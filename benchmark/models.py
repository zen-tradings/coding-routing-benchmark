"""Data models and validation shared by the benchmark."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

TIERS = ("LOW", "MID", "HIGH")
AVAILABLE_MODELS = ["claude-haiku", "claude-sonnet", "claude-opus"]
TIER_TO_MODEL = dict(zip(TIERS, AVAILABLE_MODELS))
TIER_INDEX = {tier: index for index, tier in enumerate(TIERS)}


@dataclass(frozen=True)
class Rubric:
    reasoning_depth: int
    scope: int
    context_requirement: int
    risk: int
    specialized_knowledge: int

    @property
    def score(self) -> int:
        return sum((self.reasoning_depth, self.scope, self.context_requirement, self.risk, self.specialized_knowledge))

    @property
    def expected_tier(self) -> str:
        if self.score <= 3:
            return "LOW"
        if self.score <= 7:
            return "MID"
        return "HIGH"


@dataclass(frozen=True)
class Prompt:
    id: str
    category: str
    prompt: str
    rubric: Rubric | None = None
    boundary: bool = False
    reference_model: str | None = None
    reference_rationale: str | None = None

    @property
    def expected_tier(self) -> str:
        if self.reference_model:
            return normalize_model_name(self.reference_model)[1]
        if self.rubric is None:
            raise ValueError(f"prompt {self.id} needs a reference model or rubric")
        return self.rubric.expected_tier

    @property
    def expected_model(self) -> str:
        if self.reference_model:
            return normalize_model_name(self.reference_model)[0]
        if self.rubric is None:
            raise ValueError(f"prompt {self.id} needs a reference model or rubric")
        return TIER_TO_MODEL[self.rubric.expected_tier]


@dataclass(frozen=True)
class RouteResult:
    selected_model: str | None
    selected_tier: str | None
    routing_ms: float
    raw_output: Any = None
    error: str | None = None


def normalize_model_name(value: Any) -> tuple[str, str]:
    """Convert a router model alias or tier into canonical model and tier."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("model selection must be a non-empty string")
    normalized = value.strip().lower().replace("_", "-").replace(" ", "-")
    aliases = {
        "low": ("claude-haiku", "LOW"),
        "haiku": ("claude-haiku", "LOW"),
        "claude-haiku": ("claude-haiku", "LOW"),
        "claude-3-haiku": ("claude-haiku", "LOW"),
        "claude-3-5-haiku": ("claude-haiku", "LOW"),
        "mid": ("claude-sonnet", "MID"),
        "sonnet": ("claude-sonnet", "MID"),
        "claude-sonnet": ("claude-sonnet", "MID"),
        "claude-3-sonnet": ("claude-sonnet", "MID"),
        "claude-3-5-sonnet": ("claude-sonnet", "MID"),
        "high": ("claude-opus", "HIGH"),
        "opus": ("claude-opus", "HIGH"),
        "claude-opus": ("claude-opus", "HIGH"),
        "claude-3-opus": ("claude-opus", "HIGH"),
    }
    try:
        return aliases[normalized]
    except KeyError as exc:
        raise ValueError(f"unknown model selection: {value!r}") from exc


def prompt_from_dict(value: dict[str, Any]) -> Prompt:
    required = {"id", "category", "prompt"}
    missing = required - value.keys()
    if missing:
        raise ValueError(f"prompt is missing fields: {sorted(missing)}")
    if not all(isinstance(value.get(field), str) and value[field].strip() for field in ("id", "category", "prompt")):
        raise ValueError("id, category, and prompt must be non-empty strings")

    rubric = None
    if "rubric" in value:
        rubric_data = value["rubric"]
        if not isinstance(rubric_data, dict):
            raise ValueError("rubric must be an object")
        rubric_fields = ("reasoning_depth", "scope", "context_requirement", "risk", "specialized_knowledge")
        if set(rubric_data) != set(rubric_fields):
            raise ValueError("rubric must contain exactly the five scoring dimensions")
        scores = {field: rubric_data[field] for field in rubric_fields}
        if any(not isinstance(score, int) or isinstance(score, bool) or not 0 <= score <= 2 for score in scores.values()):
            raise ValueError("each rubric dimension must be an integer from 0 to 2")
        rubric = Rubric(**scores)
        if "score" in value and value["score"] != rubric.score:
            raise ValueError(f"prompt {value.get('id')} has an incorrect score")
    elif "score" in value:
        raise ValueError("score requires a rubric")

    reference_value = value.get("reference_model")
    if reference_value is not None:
        reference_model, reference_tier = normalize_model_name(reference_value)
        if reference_model not in AVAILABLE_MODELS:
            raise ValueError(f"prompt {value.get('id')} has a model outside the available model pool")
        if "expected_tier" in value and value["expected_tier"] != reference_tier:
            raise ValueError(f"prompt {value.get('id')} has an expected_tier inconsistent with reference_model")
    else:
        if rubric is None:
            raise ValueError("prompt must include either a rubric or reference_model")
        reference_model = None
        if "expected_tier" in value and value["expected_tier"] != rubric.expected_tier:
            raise ValueError(f"prompt {value.get('id')} has an incorrect expected_tier")

    rationale = value.get("reference_rationale")
    if rationale is not None and (not isinstance(rationale, str) or not rationale.strip()):
        raise ValueError("reference_rationale must be a non-empty string when provided")
    boundary = value.get("boundary", False)
    if not isinstance(boundary, bool):
        raise ValueError("boundary must be a boolean")
    return Prompt(
        id=value["id"],
        category=value["category"],
        prompt=value["prompt"],
        rubric=rubric,
        boundary=boundary,
        reference_model=reference_model,
        reference_rationale=rationale,
    )
