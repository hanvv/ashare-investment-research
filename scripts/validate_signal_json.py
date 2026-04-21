#!/usr/bin/env python3
"""Validate an A-share research signal JSON file without external packages."""

from __future__ import annotations

import json
import sys
from pathlib import Path


TASK_TYPES = {
    "market_scan",
    "sector_scan",
    "single_stock_diagnosis",
    "watchlist_tracking",
    "portfolio_review",
}
RATINGS = {"强关注", "关注", "观察", "中性", "回避"}
RISK_LEVELS = {"low", "medium", "high", "extreme"}
DIMENSIONS = {
    "trend_volume_price",
    "fundamental_quality",
    "valuation",
    "event",
    "risk",
}


def fail(errors: list[str]) -> None:
    print("INVALID")
    for err in errors:
        print(f"- {err}")
    raise SystemExit(1)


def require(condition: bool, errors: list[str], message: str) -> None:
    if not condition:
        errors.append(message)


def is_score(value: object) -> bool:
    return isinstance(value, (int, float)) and 0 <= value <= 100


def is_confidence(value: object) -> bool:
    return isinstance(value, (int, float)) and 0 <= value <= 1


def validate_result(item: dict, idx: int, errors: list[str]) -> None:
    prefix = f"results[{idx}]"
    for key in [
        "symbol",
        "name",
        "rating",
        "total_score",
        "confidence",
        "dimension_scores",
        "core_reasons",
        "risks",
        "invalid_conditions",
        "data_quality",
    ]:
        require(key in item, errors, f"{prefix}.{key} is required")

    if "rating" in item:
        require(item["rating"] in RATINGS, errors, f"{prefix}.rating is invalid")
    if "total_score" in item:
        require(is_score(item["total_score"]), errors, f"{prefix}.total_score must be 0-100")
    if "confidence" in item:
        require(is_confidence(item["confidence"]), errors, f"{prefix}.confidence must be 0-1")

    dims = item.get("dimension_scores")
    require(isinstance(dims, dict), errors, f"{prefix}.dimension_scores must be an object")
    if isinstance(dims, dict):
        for dim in DIMENSIONS:
            require(dim in dims, errors, f"{prefix}.dimension_scores.{dim} is required")
            if dim in dims:
                require(is_score(dims[dim]), errors, f"{prefix}.dimension_scores.{dim} must be 0-100")

    for key in ["core_reasons", "risks", "invalid_conditions"]:
        value = item.get(key)
        require(isinstance(value, list), errors, f"{prefix}.{key} must be a list")
        if isinstance(value, list):
            require(len(value) > 0, errors, f"{prefix}.{key} must not be empty")

    data_quality = item.get("data_quality")
    require(isinstance(data_quality, dict), errors, f"{prefix}.data_quality must be an object")
    if isinstance(data_quality, dict):
        require(
            isinstance(data_quality.get("missing_fields", []), list),
            errors,
            f"{prefix}.data_quality.missing_fields must be a list",
        )
        require(
            is_confidence(data_quality.get("quality_score")),
            errors,
            f"{prefix}.data_quality.quality_score must be 0-1",
        )


def validate(payload: dict) -> list[str]:
    errors: list[str] = []
    for key in [
        "as_of",
        "task_type",
        "universe",
        "results",
        "methodology_version",
        "data_sources",
        "compliance_disclaimer",
    ]:
        require(key in payload, errors, f"{key} is required")

    if "task_type" in payload:
        require(payload["task_type"] in TASK_TYPES, errors, "task_type is invalid")

    require(isinstance(payload.get("universe"), dict), errors, "universe must be an object")
    require(isinstance(payload.get("data_sources"), list), errors, "data_sources must be a list")
    require(
        bool(payload.get("compliance_disclaimer")),
        errors,
        "compliance_disclaimer must not be empty",
    )

    summary = payload.get("summary")
    if summary is not None:
        require(isinstance(summary, dict), errors, "summary must be an object")
        if isinstance(summary, dict) and "risk_level" in summary:
            require(summary["risk_level"] in RISK_LEVELS, errors, "summary.risk_level is invalid")

    results = payload.get("results")
    require(isinstance(results, list), errors, "results must be a list")
    if isinstance(results, list):
        require(len(results) > 0, errors, "results must not be empty")
        for idx, item in enumerate(results):
            require(isinstance(item, dict), errors, f"results[{idx}] must be an object")
            if isinstance(item, dict):
                validate_result(item, idx, errors)

    return errors


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Usage: validate_signal_json.py <path-to-signal.json>")
        return 2

    path = Path(argv[1])
    if not path.exists():
        print(f"INVALID\n- file not found: {path}")
        return 1

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"INVALID\n- JSON parse error: {exc}")
        return 1

    if not isinstance(payload, dict):
        print("INVALID\n- root must be an object")
        return 1

    errors = validate(payload)
    if errors:
        fail(errors)

    print("VALID")
    print(f"results: {len(payload['results'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
