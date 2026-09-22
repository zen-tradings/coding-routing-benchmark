"""Machine and human readable benchmark reports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from benchmark.scoring import score_decisions


def build_summary(decisions: list[dict]) -> dict[str, Any]:
    by_router: dict[str, list[dict]] = {}
    for row in decisions:
        by_router.setdefault(row["router"], []).append(row)
    result = {router: score_decisions(rows) for router, rows in sorted(by_router.items())}
    for router, rows in by_router.items():
        categories: dict[str, list[dict]] = {}
        for row in rows:
            categories.setdefault(row["category"], []).append(row)
        result[router]["categories"] = {category: score_decisions(category_rows) for category, category_rows in sorted(categories.items())}
    return {"routers": result}


def write_summary(output_dir: Path, decisions: list[dict]) -> dict:
    summary = build_summary(decisions)
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (output_dir / "summary.md").write_text(to_markdown(summary), encoding="utf-8")
    return summary


def to_markdown(summary: dict) -> str:
    lines = ["# Pi Model Router Benchmark", "", "Agreement is measured against the human authored rubric. Failed calls are excluded from agreement and routing distribution, and reported separately.", "", "| Router | Rubric agreement | Under-route | Over-route | Median route ms | Stability | Failures |", "|---|---:|---:|---:|---:|---:|---:|"]
    for router, metrics in summary["routers"].items():
        lines.append("| {router} | {agreement} | {under} | {over} | {median} | {stability} | {failures} |".format(
            router=router,
            agreement=fmt_pct(metrics["rubric_agreement"]),
            under=fmt_pct(metrics["under_route_rate"]),
            over=fmt_pct(metrics["over_route_rate"]),
            median=fmt_num(metrics["median_routing_ms"]),
            stability=fmt_pct(metrics["mean_stability"]),
            failures=f'{metrics["failure_count"]}/{metrics["total_decisions"]}',
        ))
    lines += ["", "## Category rubric agreement", "", "| Router | " + " | ".join(sorted({category for metrics in summary["routers"].values() for category in metrics["categories"]})) + " |", "|---|" + "---:|" * len(lines[-1].split("|")[2:-1])]
    categories = sorted({category for metrics in summary["routers"].values() for category in metrics["categories"]})
    for router, metrics in summary["routers"].items():
        lines.append("| " + router + " | " + " | ".join(fmt_pct(metrics["categories"].get(category, {}).get("rubric_agreement")) for category in categories) + " |")
    lines += ["", "## Unstable prompts", ""]
    for router, metrics in summary["routers"].items():
        prompts = metrics["unstable_prompts"]
        lines.append(f"- **{router}:** {', '.join(prompts) if prompts else 'none'}")
    return "\n".join(lines) + "\n"


def fmt_pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.1f}%"


def fmt_num(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f}"
