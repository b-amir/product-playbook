#!/usr/bin/env python3
"""Minimal JSON Schema checks for plan and ledger files (stdlib only)."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


SCENARIO_ID = re.compile(r"^[A-Z][A-Z0-9]{1,5}-\d{2,3}$")


def skill_root() -> Path:
    return Path(__file__).resolve().parent.parent


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"could not read JSON: {error}") from error


def validate_plan_document(plan: Any) -> None:
    if not isinstance(plan, dict):
        raise ValueError("plan must be a JSON object")
    chapters = plan.get("chapters")
    if not isinstance(chapters, list) or not chapters:
        raise ValueError("plan must contain at least one chapter")
    seen: set[str] = set()
    for chapter in chapters:
        if not isinstance(chapter, dict):
            raise ValueError("each chapter must be an object")
        scenarios = chapter.get("scenarios")
        if not isinstance(scenarios, list) or not scenarios:
            raise ValueError("each chapter must contain scenarios")
        for scenario in scenarios:
            if not isinstance(scenario, dict):
                raise ValueError("each scenario must be an object")
            scenario_id = str(scenario.get("id", "")).strip()
            if not SCENARIO_ID.fullmatch(scenario_id):
                raise ValueError(f"invalid scenario ID: {scenario_id or '<missing>'}")
            if scenario_id in seen:
                raise ValueError(f"duplicate scenario ID: {scenario_id}")
            seen.add(scenario_id)
            steps = scenario.get("steps")
            expected = scenario.get("expected")
            if not isinstance(steps, list) or not any(str(item).strip() for item in steps):
                raise ValueError(f"scenario {scenario_id} requires steps")
            if not isinstance(expected, list) or not any(
                str(item).strip() for item in expected
            ):
                raise ValueError(f"scenario {scenario_id} requires expected results")
            viewport_sensitive = scenario.get("viewport_sensitive")
            across = scenario.get("across_viewports")
            across_items = (
                [str(item).strip() for item in across if str(item).strip()]
                if isinstance(across, list)
                else []
            )
            if viewport_sensitive is True and len(across_items) < 2:
                raise ValueError(
                    f"scenario {scenario_id} is viewport_sensitive and requires "
                    "at least two across_viewports bullets"
                )
            if across is not None and not viewport_sensitive:
                if len(across_items) < 2:
                    raise ValueError(
                        f"scenario {scenario_id} across_viewports needs at least two bullets"
                    )


def validate_ledger_document(ledger: Any, *, allow_unresolved: bool = False) -> None:
    if not isinstance(ledger, dict):
        raise ValueError("ledger must be a JSON object")
    scenarios = ledger.get("scenarios")
    if not isinstance(scenarios, dict) or not scenarios:
        raise ValueError("ledger must contain a non-empty scenarios object")
    allowed_status = {"SOURCED", "VERIFIED"}
    if allow_unresolved:
        allowed_status.add("UNRESOLVED")
    for scenario_id, entry in scenarios.items():
        if not SCENARIO_ID.fullmatch(str(scenario_id)):
            raise ValueError(f"invalid ledger scenario ID: {scenario_id}")
        if not isinstance(entry, dict):
            raise ValueError(f"ledger scenario {scenario_id} must be an object")
        status = entry.get("status", "SOURCED")
        if status not in allowed_status:
            raise ValueError(
                f"ledger scenario {scenario_id} has unsupported status: {status}"
            )
        if status == "UNRESOLVED":
            continue
        sources = entry.get("sources")
        if not isinstance(sources, list) or not sources:
            raise ValueError(f"ledger scenario {scenario_id} must cite sources")
        for raw in sources:
            if not isinstance(raw, dict):
                raise ValueError(f"ledger scenario {scenario_id} has an invalid source")
            if not str(raw.get("source_id", "")).strip():
                raise ValueError(f"ledger scenario {scenario_id} source needs source_id")
            if not str(raw.get("path", "")).strip():
                raise ValueError(f"ledger scenario {scenario_id} source needs path")


def validate_plan_file(path: Path) -> dict[str, Any]:
    plan = load_json(path)
    validate_plan_document(plan)
    return plan if isinstance(plan, dict) else {}


def validate_ledger_file(path: Path, *, allow_unresolved: bool = False) -> dict[str, Any]:
    ledger = load_json(path)
    validate_ledger_document(ledger, allow_unresolved=allow_unresolved)
    return ledger if isinstance(ledger, dict) else {}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate playbook plan or ledger JSON.")
    parser.add_argument("path", help="JSON file to validate")
    parser.add_argument(
        "--kind",
        choices=("auto", "plan", "ledger"),
        default="auto",
        help="Document kind (default: auto-detect from contents)",
    )
    parser.add_argument(
        "--allow-unresolved",
        action="store_true",
        help="Allow UNRESOLVED status in ledgers (authoring only; not for --write-state)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    path = Path(args.path).expanduser().resolve()
    if not path.is_file():
        raise SystemExit(f"not a file: {path}")
    try:
        document = load_json(path)
        kind = args.kind
        if kind == "auto":
            if isinstance(document, dict) and "chapters" in document:
                kind = "plan"
            elif isinstance(document, dict) and "scenarios" in document:
                kind = "ledger"
            else:
                raise ValueError("cannot auto-detect kind; pass --kind plan|ledger")
        if kind == "plan":
            validate_plan_document(document)
        else:
            validate_ledger_document(
                document, allow_unresolved=args.allow_unresolved
            )
    except ValueError as error:
        raise SystemExit(str(error)) from error
    print(json.dumps({"ok": True, "kind": kind, "path": str(path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
