# Coding Routing Benchmark

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**Which AI model should handle this coding task?** This benchmark measures how well different *model routers* answer that question.

A model router reads a developer's request and picks a model for it — cheap and fast for easy work, powerful for hard work. A bad router either wastes money (always picks the biggest model) or hurts quality (sends hard tasks to a weak one). This repo gives every router the **same 30 realistic coding prompts** and the **same three model choices**, then records **which model each router directly picked, how long it took, and how stable its answers are** — normalised into `LOW` / `MID` / `HIGH` tiers purely for scoring.

> **Scope of v1:** routing decisions only. The selected model is never executed and no code quality is judged. Full design notes: [`PLAN.md`](PLAN.md).

## How it works

```
30 prompts, each labelled LOW / MID / HIGH by a difficulty rubric
              │
   ┌──────────┼──────────┐
   ▼          ▼          ▼
 Router A  Router B  Router C        every router sees the same choices:
   │          │          │           LOW → claude-haiku
   ▼          ▼          ▼           MID → claude-sonnet
 each router directly returns a    HIGH → claude-opus
 model name → normalised to
 LOW/MID/HIGH tier for scoring,
 latency recorded, repeated 3×
              │
              ▼
 results.jsonl · summary.json · summary.md · metadata.json
```

Routers answer with a **model name**, never a tier — whatever a router replies (`"haiku"`, `"claude-3-5-sonnet"`, `"HIGH"`, …) is mapped to one of the three canonical models, and that model maps to a tier for scoring. The tier labels exist only so routers with different naming schemes compare directly.

**Metrics:** rubric agreement · under-routing (hard task → weak model, quality risk) · over-routing (easy task → strong model, cost waste) · decision latency (mean/median/p95) · stability across repeats · per-category breakdown. Failures (timeout, parse error, unknown model) are reported separately, never hidden. We call the main metric **rubric agreement**, not "accuracy" — expected tiers are human labels, not proven ground truth.

## Quick start

Requires **Python 3.11+**, no third-party dependencies (`pytest` for tests).

```bash
git clone https://github.com/zen-tradings/coding-routing-benchmark.git
cd coding-routing-benchmark
python3 -m benchmark.runner --dry-run     # validate prompts & config, no router calls
```

### Try it with a toy router

The benchmark talks to routers via stdin/stdout, so any script works. Save this as `toy_router.py`:

```python
#!/usr/bin/env python3
import json, sys
text = json.load(sys.stdin)["prompt"].lower()   # {"prompt": ..., "available_models": [...]}
choice = "opus" if any(w in text for w in ("design", "architecture")) else \
         "sonnet" if len(text) > 200 else "haiku"
print(json.dumps({"selected_model": choice}))
```

```bash
export PI_AUTO_ROUTER_COMMAND='python3 toy_router.py'
python3 -m benchmark.runner --router auto --runs 1 --output results/toy
cat results/toy/summary.md
```

### Example output

The `summary.md` report is a table in this shape — run the commands above to fill it with your own numbers:

| Router | Rubric agreement | Under-route | Over-route | Median route ms | Stability | Failures |
|---|---:|---:|---:|---:|---:|---:|
| pi-auto-router | …% | …% | …% | … | …% | …/30 |

Plus a per-category agreement table and a list of prompts where the router gave inconsistent answers across repeats. No official results are published yet.

### Run the full comparison

```bash
export PI_AUTO_ROUTER_COMMAND='<command for router 1>'
export PI_MODEL_ROUTER_COMMAND='<command for router 2>'
export PI_JEV_ROUTER_COMMAND='<command for router 3>'
python3 -m benchmark.runner --prompts prompts/dev_v1.jsonl --runs 3 --output results/run-001
```

30 prompts × 3 routers × 3 repetitions = 270 decisions. Since models are never executed, this costs nothing beyond what the routers themselves charge.

**CLI options:** `--prompts PATH` · `--runs N` · `--router {auto,model,jev}` (single router) · `--output DIR` · `--config PATH` (default `benchmark.toml`) · `--dry-run`.

## Plugging in your own router

The built-in adapters run the command in their environment variable once per decision. It receives on **stdin**:

```json
{"prompt": "…", "available_models": ["claude-haiku", "claude-sonnet", "claude-opus"]}
```

and answers on **stdout** with either a bare string (`sonnet`, `HIGH`) or JSON (`{"selected_model": "claude-3-5-sonnet"}`).

| Adapter | Env var |
|---|---|
| `auto` | `PI_AUTO_ROUTER_COMMAND` |
| `model` | `PI_MODEL_ROUTER_COMMAND` |
| `jev` | `PI_JEV_ROUTER_COMMAND` |

To add a router: subclass `RouterAdapter` in `benchmark/adapters/` (set `name` and `command_env`, or override `route()`), register it in the `ADAPTERS` dict, and add a `[routers.<name>]` block to `benchmark.toml`.

## The prompt set

`prompts/dev_v1.jsonl` has 30 prompts — 10 LOW, 10 MID, 10 HIGH — across ten task types (Q&A, features, debugging, tests, DevOps, refactoring, review, architecture, security, docs). Expected tiers come from a rubric scoring each prompt 0–2 on reasoning depth, scope, context, risk, and specialised knowledge (total 0–3 → LOW, 4–7 → MID, 8–10 → HIGH); the runner validates labels against it on load.

The set is **versioned benchmark data**: once results are published, `dev_v1` is frozen and changes go into `dev_v2`.

## Interpreting results

There is no single "winner" metric. Under-routing costs quality, over-routing costs money — which matters more depends on you. Tier distribution (e.g. LOW 55% / MID 38% / HIGH 7%) is a router's *fingerprint*, not a score.

## Roadmap

1. **Routing fingerprint** (this repo) — same prompts, same choices → which tier, how fast, how stable ✅
2. **Empirical sufficiency** — actually run all three models on a subset; find the *cheapest model that passes*; score routers against that
3. **Cost / latency / quality frontier** — add tokens, cost, task success
4. **Repository-aware tasks** — multi-file fixes, CI repair, refactors

## Development

```bash
python3 -m pytest
```

Contributions welcome — especially new router adapters and rubric label reviews (open an issue; `dev_v1` changes go into `dev_v2`).

## License

[MIT](LICENSE)
