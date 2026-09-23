# Reference routing policy

This is the answer-key policy for the router benchmark. It describes the intended Claude choice for a request; it is not sent to the router as part of the query. Tune the policy from your workflow and keep its version alongside each benchmark run.

| Reference model | Use when the request is… | Common examples |
|---|---|---|
| `claude-haiku` | Narrow, self-contained, and low-risk; expected work is local with familiar APIs and straightforward validation | Small helper, clear unit-test addition, formatting, bounded config edit |
| `claude-sonnet` | A normal engineering change requiring several reasoning steps, careful edge cases, or one component boundary | Module-level bug fix, API behavior change, data pipeline stage, backtest component with explicit rules |
| `claude-opus` | Ambiguous or high-risk, spans interacting components, needs substantial context or specialized domain reasoning, or has consequential failure modes | Multi-service correctness issue, point-in-time quant pipeline, distributed training/serving design with implementation requirements |

Choose from **scope, uncertainty, context burden, and impact of a wrong change**, not prompt length or a keyword such as “architecture”. A long but mechanical task can remain Haiku; a short request about a production data-loss bug can warrant Opus.

## Query authoring checklist

Every benchmark query should resemble a task a developer would actually send. Include the available artifact or context (code, schema, log, config, data shape, or acceptance behavior), the requested change, constraints, and a concrete definition of done. Keep the prompt focused on one coherent work item; multi-step work is fine when the steps belong to the same change.

Do not include the reference model, tier names, routing hints, rubric score, or this policy in the query. Store `reference_model` and `reference_rationale` as separate JSONL metadata. The adapter sends only the `prompt` field to the router.

Use source tasks from established benchmarks where they fit the intended workload. Pin the dataset release and task ID, preserve attribution and licensing, and retain enough source context for the router to estimate work. BigCodeBench's instruction split supplies practical code-generation requests with diverse function calls and tests; QF-Bench's task guidance emphasizes stateful tasks, clear deliverables, and deterministic checks; MLE-bench provides real competition tasks and resource context. These are task sources, not reference-model answer keys.

## Label review

For each query, record a short reason why the selected Claude model is the intended choice. Have a second reviewer check the high-impact and boundary cases. A disagreement indicates either an unclear prompt or an underspecified policy; resolve it before publishing the prompt set.
