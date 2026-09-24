#!/usr/bin/env python3
"""Deterministic fixture router: README toy logic plus an invalid answer on 'FAIL'."""
import json
import sys

payload = json.load(sys.stdin)
text = payload["prompt"].lower()
if "fail" in text:
    print("gpt-4")
else:
    choice = "opus" if any(w in text for w in ("design", "architecture")) else "sonnet" if len(text) > 200 else "haiku"
    print(json.dumps({"selected_model": choice, "saw_context": "context" in payload}))
