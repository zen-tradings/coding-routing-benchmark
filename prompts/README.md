# Prompt sets

Each JSONL file is a separately versioned router-selection dataset and can be passed to `benchmark.runner --prompts`. The runner forwards only prompt text to the router and records its model-name choice; it does not execute the selected model or grade task success.

- `dev_v2.jsonl`: 30 software-development tasks covering implementation, debugging, tests, operations, security, and design; 10 reference choices per Claude model.
- `quant_dev_v2.jsonl`: 30 quant-development tasks covering market data, research validity, signals, execution, risk, and controls; 10 reference choices per model.
- `mle_dev_v2.jsonl`: 30 MLE-development tasks covering data quality, feature pipelines, training, evaluation, serving, and operations; 10 reference choices per model.
- `dev_v1.jsonl`, `quant_dev_v1.jsonl`, and `mle_dev_v1.jsonl`: legacy hand-written sets retained for comparison. V1 uses rubric-derived tiers and has less detailed task context.

The v2 reference choice represents the intended routing policy, not a universal truth about model capability. Every v2 record stores `reference_model` (`claude-haiku`, `claude-sonnet`, or `claude-opus`) and a `reference_rationale`. The answer key is not sent to the router. These are professionally structured, original prompts, not literal task records copied from BigCodeBench, QF-Bench, or MLE-bench. They borrow the general practice of concrete deliverables and verifiable constraints; adding public benchmark tasks requires recording task IDs, pinned releases, attribution, and license compatibility.

The sets are balanced for inspecting model-choice behavior, not representative of production task frequencies. Their labels are policy judgments and should be reviewed by domain practitioners before using scores as a router ranking. This benchmark grades route agreement, not task completion. Keep published files unchanged and create a new version for revisions.

See [`ROUTING_POLICY.md`](ROUTING_POLICY.md) for the reference choice guidance and prompt-writing checklist.
