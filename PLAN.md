# PLAN.md — Pi Model Router Benchmark

## 1. Goal

Build a small, reproducible benchmark that compares **model-routing behavior** across Pi router implementations.

Initial routers:

- `pi-auto-router`
- `pi-model-router`
- `pi-jev-model-router`

Initial model pool:

```text
[Claude Haiku, Claude Sonnet, Claude Opus]
```

The first version is intentionally **router-only**.

We are **not** benchmarking the quality or token/sec of Haiku, Sonnet, and Opus themselves.  
For each developer prompt, we ask each router:

> Which model tier would you choose for this task?

The benchmark records the decision and routing overhead.

---

## 2. Core Questions

The benchmark should answer:

1. Which model does each router select for the same developer task?
2. How often does each router agree with the benchmark's predefined routing rubric?
3. Does a router tend to **under-route** difficult tasks?
4. Does a router tend to **over-route** simple tasks?
5. Is the routing decision stable across repeated runs?
6. How much routing latency does each router add?
7. How do routing patterns differ across different classes of developer work?

---

## 3. Non-Goals for V1

Do **not** make V1 heavy.

V1 does not:

- execute the selected Claude model
- judge generated code quality
- compare final answer quality
- measure model generation token/sec
- calculate full inference cost
- run SWE-bench or another large coding benchmark
- require repository-scale agent execution

Those can be later phases.

---

## 4. Benchmark Model Tiers

Normalize every router output into one of three tiers:

| Tier | Model | Intended use |
|---|---|---|
| `LOW` | Claude Haiku | simple, local, low-risk tasks |
| `MID` | Claude Sonnet | normal engineering tasks requiring reasoning |
| `HIGH` | Claude Opus | complex, ambiguous, high-context or architecture-heavy tasks |

Internally use canonical names:

```json
{
  "LOW": "claude-haiku",
  "MID": "claude-sonnet",
  "HIGH": "claude-opus"
}
```

Router-specific model names must be converted to these canonical tiers by adapters.

---

## 5. Prompt Taxonomy

Do not benchmark only generic "coding prompts".

Use two top-level classes.

### 5.1 Q&A / Knowledge Tasks

Developer questions that mainly require explanation rather than modification of a codebase.

Categories:

- language / syntax explanation
- framework usage
- API explanation
- debugging explanation
- architecture explanation
- tooling / CLI questions

These tasks help detect routers that over-route simple developer questions.

---

### 5.2 Actual Development Tasks

Use realistic engineering work.

#### A. Core Feature Development

Examples:

- implement a small utility function
- add a REST endpoint
- add caching
- implement pagination
- implement async worker behavior
- design a larger cross-service feature

#### B. Bug Fixing / Debugging

Examples:

- syntax/runtime error
- incorrect state handling
- async race condition
- stale cache bug
- distributed duplicate execution bug

#### C. Testing

Examples:

- write unit tests
- improve edge-case coverage
- write integration tests
- diagnose flaky tests
- design test strategy for a distributed component

#### D. DevOps / Infrastructure

Examples:

- Dockerfile change
- CI pipeline fix
- Kubernetes deployment change
- rollout / rollback strategy
- production incident configuration issue

#### E. Refactoring

Examples:

- rename / simplify a function
- extract duplicated logic
- separate business logic from persistence
- plan a multi-module refactor

#### F. Code Review

Examples:

- identify obvious bug in a patch
- review retry logic
- review concurrency safety
- review a security-sensitive change

#### G. Architecture / System Design

Examples:

- API design
- job queue design
- distributed cache
- multi-region architecture
- storage migration

#### H. Security

Examples:

- unsafe input handling
- authentication flow review
- authorization bug
- secret handling
- high-impact multi-service threat analysis

#### I. Documentation / Maintenance

Examples:

- write docstring
- update README usage
- migration notes
- contributor instructions

---

## 6. Difficulty Dimensions

Do not assign tiers using prompt length alone.

Each prompt should be annotated using a small rubric.

Score each dimension from `0` to `2`.

### Dimensions

1. **Reasoning depth**
   - 0: direct
   - 1: multi-step
   - 2: deep / ambiguous

2. **Code or system scope**
   - 0: single expression/function
   - 1: component/module
   - 2: multi-component/system

3. **Context requirement**
   - 0: self-contained
   - 1: several constraints
   - 2: broad context / interacting constraints

4. **Risk of incorrect answer**
   - 0: low
   - 1: moderate
   - 2: high

5. **Specialized knowledge**
   - 0: common
   - 1: framework/domain specific
   - 2: advanced systems/domain knowledge

Total score:

```text
0–3   -> LOW  / Haiku
4–7   -> MID  / Sonnet
8–10  -> HIGH / Opus
```

This is a **benchmark rubric**, not proven model ground truth.

Therefore the main V1 metric must be called:

> `rubric_agreement`

Do not label it "routing accuracy" yet.

---

## 7. Initial Prompt Set

Start with **30 prompts**.

Use:

```text
10 LOW
10 MID
10 HIGH
```

The set should also cover the task taxonomy.

Suggested distribution:

| Category | Count |
|---|---:|
| Q&A | 4 |
| Core feature development | 5 |
| Debugging | 4 |
| Tests | 3 |
| DevOps | 3 |
| Refactoring | 2 |
| Code review | 3 |
| Architecture | 3 |
| Security | 2 |
| Documentation | 1 |
| **Total** | **30** |

Avoid making all HIGH prompts architecture questions.

Difficulty and task type must be separate dimensions.

---

## 8. Prompt Format

Store prompts as JSONL.

Example:

```json
{
  "id": "debug-003",
  "category": "debugging",
  "prompt": "An async FastAPI endpoint occasionally serves stale cached data after an update. Identify likely causes and describe how you would debug and fix it.",
  "rubric": {
    "reasoning_depth": 1,
    "scope": 1,
    "context_requirement": 1,
    "risk": 1,
    "specialized_knowledge": 1
  },
  "score": 5,
  "expected_tier": "MID"
}
```

Keep prompts **identical across routers**.

Do not insert router-specific wording into the task itself.

---

## 9. Important Prompt-Set Rules

### Rule 1 — Realistic prompts

Bad:

```text
Design distributed cache.
```

Better:

```text
Design a cache for an API receiving high read traffic. The cache must tolerate node failure,
support invalidation after writes, and avoid serving stale authorization state. Explain the main
components and consistency trade-offs.
```

### Rule 2 — Do not leak the expected tier

Never write:

```text
This is a simple task.
```

or:

```text
Use the strongest model.
```

### Rule 3 — Avoid model-name clues

Prompts must not mention Haiku, Sonnet, Opus, cheap, expensive, small model, or large model.

### Rule 4 — Keep task intent clear

We want to benchmark routing decisions, not prompt ambiguity.

### Rule 5 — Include boundary cases

At least 20% of prompts should sit close to a tier boundary.

Example:

```text
LOW ↔ MID
MID ↔ HIGH
```

These are especially useful for comparing routers.

---

## 10. Router Adapter Design

Create one adapter per router.

```text
benchmark/
  adapters/
    base.py
    auto_router.py
    model_router.py
    jev_router.py
```

All adapters expose the same interface:

```python
class RouterAdapter:
    name: str

    def route(self, prompt: str, available_models: list[str]) -> "RouteResult":
        ...
```

Return:

```python
@dataclass
class RouteResult:
    selected_model: str
    selected_tier: str
    routing_ms: float
    raw_output: dict | str | None
    error: str | None
```

The benchmark runner must never contain router-specific parsing logic.

---

## 11. Available Model Set

Every router receives the same logical choices:

```python
AVAILABLE_MODELS = [
    "claude-haiku",
    "claude-sonnet",
    "claude-opus",
]
```

If a router uses aliases or provider-specific names, map them inside its adapter.

Example:

```python
MODEL_NORMALIZATION = {
    "haiku": "LOW",
    "claude-haiku": "LOW",
    "sonnet": "MID",
    "claude-sonnet": "MID",
    "opus": "HIGH",
    "claude-opus": "HIGH",
}
```

Do not let one router see more model choices than another.

---

## 12. Repeated Runs

Run each prompt **3 times per router**.

With:

```text
30 prompts
× 3 routers
× 3 repetitions
= 270 routing decisions
```

This is still lightweight because the selected main model is not executed.

Repeated runs reveal nondeterministic routing.

---

## 13. Metrics

### 13.1 Rubric Agreement

```text
selected_tier == expected_tier
```

Report:

```text
rubric_agreement = matching decisions / total decisions
```

---

### 13.2 Under-Routing

Examples:

```text
expected MID  -> selected LOW
expected HIGH -> selected MID
expected HIGH -> selected LOW
```

Track:

```text
under_route_rate
```

Also track severity:

```text
HIGH -> LOW = under-route by 2 tiers
```

---

### 13.3 Over-Routing

Examples:

```text
expected LOW -> selected MID
expected LOW -> selected HIGH
expected MID -> selected HIGH
```

Track:

```text
over_route_rate
```

This is important for cost-sensitive routing.

---

### 13.4 Routing Latency

Measure only the router decision when possible:

```text
router_start
    ↓
routing decision
    ↓
router_end
```

Store:

```text
routing_ms
```

Report:

- mean
- median
- p95

Do not mix model generation latency into this metric.

---

### 13.5 Routing Stability

For the three repeated runs:

```text
Haiku
Haiku
Haiku
```

is fully stable.

```text
Haiku
Sonnet
Haiku
```

is unstable.

Per prompt:

```text
stability = count(most_common_selection) / number_of_runs
```

Overall report:

```text
mean_stability
```

Also list every prompt where the router selected multiple tiers.

---

### 13.6 Tier Distribution

Report how frequently each router chooses:

```text
LOW
MID
HIGH
```

This quickly exposes router personality.

Example:

```text
Router A:
LOW  55%
MID  38%
HIGH  7%
```

This should not itself be treated as a quality score.

---

## 14. Results Schema

Write every decision to `results.jsonl`.

Example:

```json
{
  "run_id": "2026-09-22T16:40:00Z",
  "router": "pi-jev-model-router",
  "prompt_id": "debug-003",
  "category": "debugging",
  "expected_tier": "MID",
  "selected_model": "claude-sonnet",
  "selected_tier": "MID",
  "routing_ms": 41.7,
  "repeat": 2,
  "match": true,
  "tier_delta": 0,
  "error": null
}
```

Tier encoding:

```text
LOW  = 0
MID  = 1
HIGH = 2
```

Then:

```text
tier_delta = selected - expected
```

Interpretation:

```text
-2 = heavy under-route
-1 = under-route
 0 = rubric match
+1 = over-route
+2 = heavy over-route
```

---

## 15. Summary Output

Generate `summary.json` and `summary.md`.

Example table:

| Router | Rubric agreement | Under-route | Over-route | Median route ms | Stability |
|---|---:|---:|---:|---:|---:|
| auto-router | — | — | — | — | — |
| model-router | — | — | — | — | — |
| jev-router | — | — | — | — | — |

Also generate category-level breakdown:

| Router | Q&A | Feature | Debug | Tests | DevOps | Review | Architecture |
|---|---:|---:|---:|---:|---:|---:|---:|

Do not declare an overall "winner" from one metric.

The report should expose trade-offs.

---

## 16. Suggested Repository Structure

```text
router-benchmark/
├── PLAN.md
├── README.md
├── pyproject.toml
├── benchmark/
│   ├── __init__.py
│   ├── runner.py
│   ├── scoring.py
│   ├── reporting.py
│   ├── models.py
│   └── adapters/
│       ├── __init__.py
│       ├── base.py
│       ├── auto_router.py
│       ├── model_router.py
│       └── jev_router.py
├── prompts/
│   ├── dev_v1.jsonl
│   └── README.md
├── results/
│   └── .gitkeep
└── tests/
    ├── test_scoring.py
    ├── test_prompt_schema.py
    └── test_model_normalization.py
```

---

## 17. CLI

Keep the interface simple.

Run all routers:

```bash
python -m benchmark.runner \
  --prompts prompts/dev_v1.jsonl \
  --runs 3 \
  --output results/run-001
```

Run one router:

```bash
python -m benchmark.runner \
  --router jev \
  --prompts prompts/dev_v1.jsonl \
  --runs 3 \
  --output results/jev-run
```

Dry run:

```bash
python -m benchmark.runner \
  --prompts prompts/dev_v1.jsonl \
  --dry-run
```

Dry run should validate:

- prompt schema
- tier scores
- adapter availability
- model normalization

without executing router calls.

---

## 18. Configuration

Use one config file for model choices and router settings.

Example:

```toml
[benchmark]
runs = 3
timeout_seconds = 10

[models]
low = "claude-haiku"
mid = "claude-sonnet"
high = "claude-opus"

[routers.auto]
enabled = true

[routers.model]
enabled = true

[routers.jev]
enabled = true
```

API keys or credentials must come from environment variables.

Never commit secrets.

---

## 19. Error Handling

A router failure must not abort the benchmark.

Record:

```json
{
  "selected_model": null,
  "selected_tier": null,
  "routing_ms": 10000,
  "error": "timeout"
}
```

Classify at minimum:

```text
timeout
invalid_model
parse_error
router_error
configuration_error
```

Report failure rate separately.

Do not silently convert router errors into a default tier.

---

## 20. Reproducibility

Each benchmark run should record:

```text
timestamp
git commit
prompt set version
router package/version
router configuration
number of repetitions
available model list
runtime version
platform
```

Save this as:

```text
results/<run>/metadata.json
```

This matters because router implementations and model catalogs can change quickly.

---

## 21. Prompt Versioning

Treat the prompt set as benchmark data.

Start with:

```text
dev_v1
```

Do not edit it after publishing results.

For changes create:

```text
dev_v2
dev_v3
```

Each prompt should have a permanent ID.

---

## 22. Human Review of the Rubric

Before running the official comparison:

1. Create the 30 prompts.
2. Independently review expected tiers.
3. Resolve obvious disagreements.
4. Mark ambiguous prompts as `boundary=true`.

Example:

```json
{
  "id": "review-004",
  "expected_tier": "MID",
  "boundary": true
}
```

Report results both:

```text
all prompts
non-boundary prompts only
```

This reduces the effect of questionable human labels.

---

## 23. V1 Implementation Sequence

### Step 1 — Scaffold

Create:

- package structure
- schemas
- config
- CLI

### Step 2 — Prompt Dataset

Create `prompts/dev_v1.jsonl` with 30 prompts.

Validate:

```text
10 LOW
10 MID
10 HIGH
```

and broad category coverage.

### Step 3 — Adapter Interface

Implement `RouterAdapter` and normalized `RouteResult`.

### Step 4 — Router Integrations

Implement:

- auto-router adapter
- model-router adapter
- Jev-router adapter

Each must return the same canonical model/tier representation.

### Step 5 — Benchmark Runner

For every:

```text
router
× prompt
× repetition
```

record the decision independently.

### Step 6 — Scoring

Compute:

- rubric agreement
- tier delta
- under-route rate
- over-route rate
- stability
- latency
- failure rate

### Step 7 — Reporting

Produce:

```text
results.jsonl
summary.json
summary.md
metadata.json
```

### Step 8 — Tests

Unit-test:

- tier conversion
- prompt score validation
- model-name normalization
- under/over-routing calculation
- stability calculation
- malformed router output

### Step 9 — First Run

Run all three routers on `dev_v1`.

Do not change prompts after seeing router results.

---

## 24. Acceptance Criteria for V1

V1 is complete when:

- [ ] the same 30 prompts can be sent to all routers
- [ ] available models are restricted to Haiku / Sonnet / Opus
- [ ] every router decision is normalized into LOW / MID / HIGH
- [ ] routing latency is captured
- [ ] every prompt is run 3 times
- [ ] failures are recorded instead of crashing the run
- [ ] rubric agreement is calculated
- [ ] under-routing and over-routing are separated
- [ ] routing stability is calculated
- [ ] results are saved in machine-readable JSONL
- [ ] a human-readable Markdown summary is generated
- [ ] run metadata makes results reproducible

---

## 25. Phase 2 — Validate Whether the Selected Tier Was Actually Sufficient

V1 measures router behavior against a predefined rubric.

It does **not** prove that the expected tier is optimal.

Phase 2 should execute all three models on a subset of prompts:

```text
prompt
  ├── Haiku
  ├── Sonnet
  └── Opus
```

Then evaluate task success.

The target becomes:

> Find the lowest-cost model that completes the task successfully.

Example:

```text
Haiku  -> fail
Sonnet -> pass
Opus   -> pass

empirical optimal tier = MID
```

Only after this phase should we begin discussing **empirical routing accuracy**.

---

## 26. Phase 3 — Cost / Latency / Quality Frontier

Once model execution is enabled, add:

```text
time to first token
output tokens/sec
total latency
input tokens
output tokens
estimated cost
task success
```

Then compare routing strategies on the actual objective:

```text
quality
vs
cost
vs
latency
```

The ideal router is not simply the one that chooses the strongest model most often.

It should choose the **least expensive / fastest model that still solves the task successfully**.

---

## 27. Phase 4 — Repository-Aware Dev Tasks

Only after the lightweight benchmark works, consider real repository tasks:

```text
bug fixing
feature implementation
test repair
CI failure
multi-file refactor
```

This can later integrate with agent or SWE-style benchmarks.

Do not start here.

---

## 28. Main Principle

Keep V1 narrow:

```text
same prompt
same available models
same conditions
        ↓
different router
        ↓
which tier did it choose?
how long did routing take?
how stable was the choice?
```

The first benchmark should give us a **clear routing fingerprint** for each implementation before we spend money and compute on full model execution.
