# Prompt sets

Each JSONL file is a separately versioned router-selection dataset and can be passed to `benchmark.runner --prompts`. The runner forwards only prompt text to the router and records its model-name choice; it does not execute the selected model or grade task success.

- `dev_v2.jsonl`: 30 software-development tasks covering implementation, debugging, tests, operations, security, and design; 10 reference choices per Claude model.
- `quant_dev_v2.jsonl`: 30 quant-development tasks covering market data, research validity, signals, execution, risk, and controls; 10 reference choices per model.
- `mle_dev_v2.jsonl`: 30 MLE-development tasks covering data quality, feature pipelines, training, evaluation, serving, and operations; 10 reference choices per model.
- `dev_v1.jsonl`, `quant_dev_v1.jsonl`, and `mle_dev_v1.jsonl`: legacy hand-written sets retained for comparison. V1 uses rubric-derived tiers and has less detailed task context.

The v2 reference choice represents the intended routing policy, not a universal truth about model capability. Every v2 record stores `reference_model` (`claude-haiku`, `claude-sonnet`, or `claude-opus`) and a `reference_rationale`. The answer key is not sent to the router. These are professionally structured, original prompts, not literal task records copied from BigCodeBench, QF-Bench, or MLE-bench. They borrow the general practice of concrete deliverables and verifiable constraints; adding public benchmark tasks requires recording task IDs, pinned releases, attribution, and license compatibility.

The sets are balanced for inspecting model-choice behavior, not representative of production task frequencies. Their labels are policy judgments and should be reviewed by domain practitioners before using scores as a router ranking. This benchmark grades route agreement, not task completion. Keep published files unchanged and create a new version for revisions.

See [`ROUTING_POLICY.md`](ROUTING_POLICY.md) for the reference choice guidance and prompt-writing checklist.

## Optional second-labeler file

To measure how reliable the reference labels are, a second person can label a set independently. Put their labels next to the prompt file as `<set>.labels_b.jsonl`. For `prompts/dev_v2.jsonl` that is `prompts/dev_v2.labels_b.jsonl`. Each line has exactly these fields:

```json
{"id": "dev2-001", "reference_model": "claude-haiku", "rationale": "Bounded parser change with explicit limits."}
```

- `id` must match a prompt in the set. Prompts without a line are listed as uncovered and left out of the comparison.
- `reference_model` accepts the same names as prompt files (`claude-haiku`, `sonnet`, `HIGH`, …).
- The second labeler should not see the first labeler's `reference_model` or `reference_rationale` before labeling.

When the file exists, the runner reports labeler agreement, Cohen's kappa, every prompt the labelers disagree on, and each router's agreement on only the prompts where both labelers agree. Adding a labels file does not change a published prompt file, so it can be added to an existing version. No second-label files are committed yet.

## Optional structured context

Future prompt versions may add a `context` object that describes the task's surroundings:

```json
{"id": "dev3-001", "category": "debugging", "prompt": "…", "reference_model": "claude-sonnet", "reference_rationale": "…",
 "context": {"files_touched": ["src/cache.py", "tests/test_cache.py"], "has_tests": true, "repo_size_loc": 42000}}
```

| Field | Type |
|---|---|
| `files_touched` | list of non-empty strings |
| `has_tests` | boolean |
| `repo_size_loc` | non-negative integer |

Other keys are allowed if they are valid JSON. The runner adds `"context"` to the router's stdin payload **only when a prompt has one**, so routers that ignore it keep working. Existing v1 and v2 files have no context and must not be edited to add it; put context in a new version.

## Held-out (private) prompt sets

A public prompt set can leak into router tuning. To keep a set that is never committed:

1. Put it under `prompts/private/` (ignored by git), or anywhere outside the repo.
2. Run it with `--prompts /path/to/private.jsonl`, or set `ROUTING_BENCHMARK_PROMPTS=/path/to/private.jsonl` and omit `--prompts`.
3. The run's `metadata.json` records `"held_out": true`, the file name, and its SHA-256. The path and contents are not recorded, so a published result can be tied to a fixed private file without revealing it.

`results.jsonl` includes each prompt's id, category, reference model, and rationale, so treat held-out run outputs as private too. The `results/` folder is already git-ignored. A private second-labeler file goes next to the private prompt file (for example `prompts/private/holdout_v1.labels_b.jsonl`).
