# Pi Model Router Benchmark

This repository benchmarks router decisions only. It sends the same developer prompts to each configured Pi router, normalizes the selected model into `LOW`, `MID`, or `HIGH`, records decision latency, and produces JSONL, JSON, and Markdown reports. It does not execute the selected Claude model.

## Run validation

```bash
python3 -m benchmark.runner --prompts prompts/dev_v1.jsonl --dry-run
```

## Run a benchmark

Defaults such as repetitions, timeout, canonical model choices, and enabled routers live in [`benchmark.toml`](benchmark.toml). Each external router is configured with an environment variable containing its command. The command receives JSON on stdin:

```json
{"prompt":"...","available_models":["claude-haiku","claude-sonnet","claude-opus"]}
```

It must write either a model/tier string or JSON such as `{"selected_model":"sonnet"}` to stdout.

```bash
export PI_AUTO_ROUTER_COMMAND='your-auto-router-command'
export PI_MODEL_ROUTER_COMMAND='your-model-router-command'
export PI_JEV_ROUTER_COMMAND='your-jev-router-command'
python3 -m benchmark.runner --prompts prompts/dev_v1.jsonl --runs 3 --output results/run-001
```

Use `--router auto`, `--router model`, or `--router jev` to run one adapter. A missing command is recorded as `configuration_error` and does not abort the run.

## Test

```bash
python3 -m pytest
```
