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
    parser.add_argument(
        "--tests-dir",
        help="Generated runnable tests folder to score (playbook-tests.json)",
    )
    return parser.parse_args()


def load_expected(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def score_tests(tests_dir: Path, ids: list[str], expected: dict[str, Any]) -> list[str]:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import playbook_tests

    try:
        config = playbook_tests.load_config(tests_dir)
    except (ValueError, json.JSONDecodeError) as error:
        return [f"tests: {error}"]
    failures = [f"tests: {m}" for m in playbook_tests.check_config(config, tests_dir, set(ids))]
    scenarios = config.get("scenarios", {})
    for scenario_id in expected.get("required_automated_ids", []):
        entry = scenarios.get(scenario_id)
        if not entry or entry.get("manual_only"):
            failures.append(f"tests: {scenario_id} has no runnable test")
    for ref in expected.get("required_acceptance_ids", []):
        if not any(ref in (e.get("acceptance") or []) for e in scenarios.values()):
            failures.append(f"tests: acceptance {ref} is not mapped to a scenario")
    for path in tests_dir.rglob("*"):
        if path.is_file() and path.suffix in {".py", ".ts", ".js", ".sh", ".json"}:
            text = path.read_text(encoding="utf-8", errors="ignore")
            for needle in expected.get("forbidden_test_substrings", []):
                if needle in text:
                    failures.append(f"tests: forbidden {needle!r} in {path.name}")
    return failures


def score(
    playbook: Path, expected: dict[str, Any], tests_dir: Path | None = None
) -> dict[str, Any]:
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

    headings = re.findall(r"^## ([A-Z][A-Z0-9]{1,5}-\d{2,3}):", combined, re.M)
    if tests_dir is not None:
        failures.extend(score_tests(tests_dir, headings, expected))

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
    tests_dir = Path(args.tests_dir).expanduser().resolve() if args.tests_dir else None
    result = score(playbook, load_expected(expected_path), tests_dir)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
