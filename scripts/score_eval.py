#!/usr/bin/env python3
"""Score a generated playbook against evals/expected.json."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Score a product-playbook eval run.")
    parser.add_argument(
        "playbook_dir",
        help="Generated playbook directory to score",
    )
    parser.add_argument(
        "--expected",
        default=str(Path(__file__).resolve().parent.parent / "evals" / "expected.json"),
        help="Expectations JSON (default: evals/expected.json)",
    )
    return parser.parse_args()


def load_expected(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def score(playbook: Path, expected: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    markdown_files = sorted(path for path in playbook.glob("*.md") if path.is_file())
    combined = "\n".join(path.read_text(encoding="utf-8") for path in markdown_files)

    for scenario_id in expected.get("required_scenario_ids", []):
        if not re.search(rf"^## {re.escape(scenario_id)}:", combined, re.M):
            failures.append(f"missing scenario {scenario_id}")

    for needle in expected.get("required_substrings", []):
        if needle not in combined:
            failures.append(f"missing substring: {needle}")

    for needle in expected.get("forbidden_substrings", []):
        if needle in combined:
            failures.append(f"forbidden substring present: {needle}")

    state_path = playbook / ".product-playbook-state.json"
    if not state_path.is_file():
        failures.append("missing .product-playbook-state.json")
    else:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        for key, value in expected.get("required_state", {}).items():
            if state.get(key) != value:
                failures.append(f"state.{key} expected {value!r}, got {state.get(key)!r}")

    allowed_names = set(expected.get("allowed_playbook_basenames", []))
    globs = expected.get("allowed_playbook_globs", [])
    for path in playbook.iterdir():
        if not path.is_file():
            if path.name not in {".", ".."}:
                # ignore empty dirs? flag unexpected dirs except none expected
                if path.name not in {"playbook-findings"}:
                    failures.append(f"unexpected entry: {path.name}")
            continue
        if path.name in allowed_names:
            continue
        if any(path.match(pattern) for pattern in globs):
            continue
        if path.name in {"playbook.pdf", "playbook.html"}:
            continue
        failures.append(f"unexpected file in playbook: {path.name}")

    return {
        "ok": not failures,
        "failures": failures,
        "playbook": str(playbook),
        "scenario_headings": re.findall(r"^## ([A-Z][A-Z0-9]{1,5}-\d{2,3}):", combined, re.M),
    }


def main() -> int:
    args = parse_args()
    playbook = Path(args.playbook_dir).expanduser().resolve()
    expected_path = Path(args.expected).expanduser().resolve()
    if not playbook.is_dir():
        raise SystemExit(f"playbook dir missing: {playbook}")
    result = score(playbook, load_expected(expected_path))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
