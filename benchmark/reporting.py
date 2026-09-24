"""Machine and human readable benchmark reports."""

from __future__ import annotations

import json
from itertools import combinations
from pathlib import Path
from typing import Any

from benchmark.config import DEFAULT_BOOTSTRAP, DEFAULT_WEIGHTING
from benchmark.models import TIERS
from benchmark.scoring import bootstrap_ci, intervals_overlap, score_decisions, score_extended

WEIGHTING_ASSUMPTION = (
    "Target tier shares are an assumption about a realistic workload, not measured data. "
    "Configure them in [weighting] in benchmark.toml."
)
DEFAULT_SHARES = {tier.upper(): share for tier, share in DEFAULT_WEIGHTING.items()}


def build_summary(
    decisions: list[dict],
    *,
    prices: dict[str, float] | None = None,
    target_shares: dict[str, float] | None = None,
    bootstrap: dict[str, int] | None = None,
    baselines: set[str] | frozenset[str] = frozenset(),
    labeler: dict | None = None,
    skipped_routers: dict[str, str] | None = None,
) -> dict[str, Any]:
    shares = target_shares or DEFAULT_SHARES
    bootstrap = bootstrap or DEFAULT_BOOTSTRAP
    by_router: dict[str, list[dict]] = {}
    for row in decisions:
        by_router.setdefault(row["router"], []).append(row)
    result = {router: score_decisions(rows) for router, rows in sorted(by_router.items())}
    for router, rows in by_router.items():
        categories: dict[str, list[dict]] = {}
        for row in rows:
            categories.setdefault(row["category"], []).append(row)
        result[router]["categories"] = {category: score_decisions(category_rows) for category, category_rows in sorted(categories.items())}
        # Additions below; the keys above keep their original values.
        extended = score_extended(rows, prices, shares)
        extended.pop("agreement")  # identical to reference_model_agreement
        extended["reweighted"]["reference_model_agreement"] = extended["reweighted"].pop("agreement")
        result[router]["baseline"] = router in baselines
        result[router].update(extended)
        result[router]["ci95"] = bootstrap_ci(rows, bootstrap["iterations"], bootstrap["seed"])
    return {
        "routers": result,
        "weighting": {
            "target_shares": shares,
            "assumption": WEIGHTING_ASSUMPTION,
            "observed_reference_shares": observed_reference_shares(decisions),
        },
        "cost_model": None if prices is None else {
            "blended_price_per_mtok": prices,
            "note": "Blended price = input + output USD per million tokens from benchmark.toml; only ratios matter.",
        },
        "bootstrap": {"iterations": bootstrap["iterations"], "seed": bootstrap["seed"], "level": 0.95, "resample_unit": "prompt"},
        "significance": significance(result, by_router),
        "labeler_agreement": labeler,
        "skipped_routers": skipped_routers or {},
    }


def observed_reference_shares(decisions: list[dict]) -> dict[str, float]:
    tiers = {row["prompt_id"]: row["expected_tier"] for row in decisions}
    return {tier: (sum(value == tier for value in tiers.values()) / len(tiers) if tiers else 0.0) for tier in TIERS}


def significance(result: dict, by_router: dict[str, list[dict]]) -> list[dict]:
    pairs = []
    for first, second in combinations(result, 2):
        ci_a, ci_b = result[first]["ci95"]["agreement"], result[second]["ci95"]["agreement"]
        overlap = intervals_overlap(ci_a, ci_b)
        if overlap is None:
            continue
        prompts = min(len({row["prompt_id"] for row in by_router[name]}) for name in (first, second))
        pairs.append({
            "router_a": first,
            "router_b": second,
            "agreement_a": result[first]["reference_model_agreement"],
            "agreement_b": result[second]["reference_model_agreement"],
            "ci_a": ci_a,
            "ci_b": ci_b,
            "intervals_overlap": overlap,
            "prompts": prompts,
        })
    return pairs


def write_summary(output_dir: Path, decisions: list[dict], **options: Any) -> dict:
    summary = build_summary(decisions, **options)
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (output_dir / "summary.md").write_text(to_markdown(summary), encoding="utf-8")
    return summary


def display_order(summary: dict) -> list[str]:
    routers = summary["routers"]
    return [name for name in routers if not routers[name].get("baseline")] + [name for name in routers if routers[name].get("baseline")]


def label(router: str, metrics: dict) -> str:
    return f"{router} *(baseline)*" if metrics.get("baseline") else router


def to_markdown(summary: dict) -> str:
    order = display_order(summary)
    routers = summary["routers"]
    shares = summary.get("weighting", {}).get("target_shares", DEFAULT_SHARES)
    share_text = " / ".join(f"{tier} {shares.get(tier, 0) * 100:.0f}%" for tier in TIERS)
    lines = [
        "# Pi Model Router Benchmark",
        "",
        "Reference-model agreement compares the selected model with the reference choice in the prompt set. When no explicit reference model is stored, the reference is derived from the prompt rubric. Failed calls are excluded from agreement and routing distribution, and reported separately.",
        "",
        "| Router | Agreement (95% CI) | Reweighted agreement | Mean tier distance | Cost-weighted error | Median route ms | Stability | Failures |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for router in order:
        metrics = routers[router]
        ci = metrics.get("ci95", {})
        lines.append("| {router} | {agreement} | {reweighted} | {distance} | {cost} | {median} | {stability} | {failures} |".format(
            router=label(router, metrics),
            agreement=fmt_pct_ci(metrics["rubric_agreement"], ci.get("agreement")),
            reweighted=fmt_pct(metrics.get("reweighted", {}).get("reference_model_agreement")),
            distance=fmt_num(metrics.get("mean_tier_distance")),
            cost=fmt_pct(metrics.get("cost_weighted_error")),
            median=fmt_num(metrics["median_routing_ms"]),
            stability=fmt_pct(metrics["mean_stability"]),
            failures=f'{metrics["failure_count"]}/{metrics["total_decisions"]}',
        ))
    lines += [
        "",
        f"- **Reweighted** columns weight reference tiers to {share_text}. **This distribution is an assumption, not measured data.**",
        "- **Mean tier distance** is |chosen tier − reference tier| (LOW=0, MID=1, HIGH=2), averaged over successful decisions.",
        "- **Cost-weighted error** is the mean |chosen price − reference price| / reference price, using the per-model prices in benchmark.toml. Over-routing can exceed 100%; under-routing cannot.",
        "- Rows marked *(baseline)* are built-in reference routers, not candidate routers.",
    ]
    if summary.get("cost_model") is None:
        lines.append("- Cost metrics are blank because no [prices] block is configured.")
    for router, reason in summary.get("skipped_routers", {}).items():
        lines.append(f"- Skipped **{router}**: {reason}.")

    lines += [
        "",
        "### Routing errors",
        "",
        "| Router | Under-route (95% CI) | Over-route (95% CI) | Tier distance (95% CI) | Under distance | Over distance | Reweighted under | Reweighted over | Reweighted distance | Reweighted cost error | Cost ratio |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for router in order:
        metrics = routers[router]
        ci = metrics.get("ci95", {})
        reweighted = metrics.get("reweighted", {})
        lines.append("| " + " | ".join([
            label(router, metrics),
            fmt_pct_ci(metrics["under_route_rate"], ci.get("under_route_rate")),
            fmt_pct_ci(metrics["over_route_rate"], ci.get("over_route_rate")),
            fmt_num_ci(metrics.get("mean_tier_distance"), ci.get("mean_tier_distance")),
            fmt_num(metrics.get("mean_under_distance")),
            fmt_num(metrics.get("mean_over_distance")),
            fmt_pct(reweighted.get("under_route_rate")),
            fmt_pct(reweighted.get("over_route_rate")),
            fmt_num(reweighted.get("mean_tier_distance")),
            fmt_pct(reweighted.get("cost_weighted_error")),
            fmt_num(metrics.get("cost_ratio")),
        ]) + " |")
    lines += [
        "",
        "Under and over distance are averaged over all successful decisions, so they sum to the tier distance. Cost ratio is total chosen-model price / total reference-model price (1.00 = same spend).",
    ]

    categories = sorted({category for metrics in routers.values() for category in metrics["categories"]})
    lines += ["", "## Category reference-model agreement", "", "| Router | " + " | ".join(categories) + " |", "|---|" + "---:|" * len(categories)]
    for router in order:
        metrics = routers[router]
        lines.append("| " + label(router, metrics) + " | " + " | ".join(fmt_pct(metrics["categories"].get(category, {}).get("rubric_agreement")) for category in categories) + " |")

    pairs = summary.get("significance", [])
    lines += ["", "## Significance", ""]
    if pairs:
        lines.append("95% bootstrap intervals resample prompts ({iterations} iterations, seed {seed}). Overlapping intervals are a conservative check: they mean the difference is not established at this sample size.".format(**summary["bootstrap"]))
        lines.append("")
        for pair in pairs:
            if pair["intervals_overlap"]:
                lines.append(f"- **{pair['router_a']}** vs **{pair['router_b']}**: agreement {fmt_pct(pair['agreement_a'])} vs {fmt_pct(pair['agreement_b'])} is not distinguishable at n={pair['prompts']} prompts (95% CIs overlap).")
        distinct = [f"{pair['router_a']} vs {pair['router_b']}" for pair in pairs if not pair["intervals_overlap"]]
        lines.append(f"- Non-overlapping agreement intervals: {', '.join(distinct) if distinct else 'none'}.")
    else:
        lines.append("Fewer than two routers produced successful decisions; no comparisons.")

    labeler = summary.get("labeler_agreement")
    if labeler:
        lines += [
            "",
            "## Labeler agreement",
            "",
            f"Second labels from `{labeler['source']}` cover {labeler['prompts_compared']} prompts. "
            f"Labeler agreement: {fmt_pct(labeler['agreement'])}; Cohen's kappa: {fmt_num(labeler['cohens_kappa'])}; "
            f"prompts where both labelers agree: {labeler['consensus_prompts']}.",
        ]
        if labeler["prompts_missing_labeler_b"]:
            lines.append(f"Prompts without a second label: {', '.join(labeler['prompts_missing_labeler_b'])}.")
        lines += ["", "| Router | Agreement on consensus prompts |", "|---|---:|"]
        for router in order:
            value = labeler["router_agreement_on_consensus"].get(router)
            lines.append(f"| {label(router, routers[router])} | {fmt_pct(value['agreement'] if value else None)} |")
        lines += ["", "Disagreements:", ""]
        if labeler["disagreements"]:
            lines += [f"- `{item['prompt_id']}`: labeler A {item['labeler_a']}, labeler B {item['labeler_b']}" for item in labeler["disagreements"]]
        else:
            lines.append("- none")

    lines += ["", "## Unstable prompts", ""]
    for router in order:
        prompts = routers[router]["unstable_prompts"]
        lines.append(f"- **{label(router, routers[router])}:** {', '.join(prompts) if prompts else 'none'}")
    return "\n".join(lines) + "\n"


def fmt_pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.1f}%"


def fmt_num(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f}"


def fmt_pct_ci(value: float | None, interval: list[float] | None) -> str:
    if value is None or interval is None:
        return fmt_pct(value)
    return f"{fmt_pct(value)} ({interval[0] * 100:.1f}–{interval[1] * 100:.1f})"


def fmt_num_ci(value: float | None, interval: list[float] | None) -> str:
    if value is None or interval is None:
        return fmt_num(value)
    return f"{fmt_num(value)} ({interval[0]:.2f}–{interval[1]:.2f})"
