#!/usr/bin/env python3
"""Render a deterministic tester-facing playbook from an evidence-backed plan."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render a new product playbook from a JSON scenario plan."
    )
    parser.add_argument("plan", help="Evidence-backed JSON plan")
    parser.add_argument("output_dir", help="New playbook directory")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow replacement of Markdown files in the destination.",
    )
    return parser.parse_args()


def read_plan(path: Path) -> dict[str, Any]:
    from schema_utils import validate_plan_file

    return validate_plan_file(path)


def text(value: Any, fallback: str) -> str:
    result = str(value or "").strip()
    return result or fallback


def lines(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return normalized or "journey"


def validate_plan(plan: dict[str, Any]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for chapter_index, chapter in enumerate(plan["chapters"], start=1):
        if not isinstance(chapter, dict):
            raise ValueError("each chapter must be an object")
        title = text(chapter.get("title"), f"Journey {chapter_index}")
        scenarios = chapter.get("scenarios")
        if not isinstance(scenarios, list) or not scenarios:
            raise ValueError(f"chapter {title} must contain scenarios")
        normalized_scenarios: list[dict[str, Any]] = []
        for scenario in scenarios:
            if not isinstance(scenario, dict):
                raise ValueError(f"chapter {title} has an invalid scenario")
            scenario_id = text(scenario.get("id"), "")
            if not re.fullmatch(r"[A-Z][A-Z0-9]{1,5}-\d{2,3}", scenario_id):
                raise ValueError(f"invalid scenario ID: {scenario_id or '<missing>'}")
            if scenario_id in seen:
                raise ValueError(f"duplicate scenario ID: {scenario_id}")
            seen.add(scenario_id)
            steps = lines(scenario.get("steps"))
            expected = lines(scenario.get("expected"))
            if not steps or not expected:
                raise ValueError(f"scenario {scenario_id} requires steps and expected results")
            normalized_scenarios.append(
                {
                    **scenario,
                    "id": scenario_id,
                    "title": text(scenario.get("title"), "Observable outcome"),
                    "goal": text(scenario.get("goal"), scenario.get("title", "Complete the journey")),
                    "who": text(scenario.get("who"), "Tester"),
                    "steps": steps,
                    "expected": expected,
                    "setup": lines(scenario.get("setup")),
                    "cleanup": lines(scenario.get("cleanup")),
                    "notes": lines(scenario.get("notes")),
                }
            )
        normalized.append(
            {
                **chapter,
                "title": title,
                "intro": text(
                    chapter.get("intro"),
                    "Run these scenarios through the supported product interface.",
                ),
                "scenarios": normalized_scenarios,
            }
        )
    return normalized


def bullet_section(label: str, values: list[str]) -> list[str]:
    if not values:
        return []
    return [f"**{label}**", "", *(f"- {value}" for value in values), ""]


def render_chapter(chapter: dict[str, Any], next_target: str) -> str:
    output = [
        f"# {chapter['title']}",
        "",
        chapter["intro"],
        "",
        "## Scenario list",
        "",
        "| ID | Scenario | Persona |",
        "| --- | --- | --- |",
    ]
    for scenario in chapter["scenarios"]:
        output.append(
            f"| {scenario['id']} | {scenario['title']} | {scenario['who']} |"
        )
    output.append("")
    for scenario in chapter["scenarios"]:
        output.extend(
            [
                f"## {scenario['id']}: {scenario['title']}",
                "",
                "**Goal**",
                "",
                scenario["goal"],
                "",
                "**Who**",
                "",
                scenario["who"],
                "",
            ]
        )
        output.extend(bullet_section("Setup", scenario["setup"]))
        output.extend(["**Steps**", ""])
        output.extend(
            f"{index}. {value}" for index, value in enumerate(scenario["steps"], start=1)
        )
        output.extend(["", "**Expected**", ""])
        output.extend(f"- {value}" for value in scenario["expected"])
        output.append("")
        output.extend(bullet_section("Cleanup", scenario["cleanup"]))
        output.extend(bullet_section("Note", scenario["notes"]))
    output.extend(["## Chapter checklist", "", "```text"])
    output.extend(scenario["id"] for scenario in chapter["scenarios"])
    output.extend(["```", "", f"[Continue]({next_target})", ""])
    return "\n".join(output)


def render_readme(plan: dict[str, Any], chapters: list[dict[str, Any]], files: list[str]) -> str:
    scenario_ids = [
        scenario["id"] for chapter in chapters for scenario in chapter["scenarios"]
    ]
    smoke = lines(plan.get("smoke_path")) or scenario_ids[: min(3, len(scenario_ids))]
    actors = lines(plan.get("actors")) or sorted(
        {scenario["who"] for chapter in chapters for scenario in chapter["scenarios"]}
    )
    setup = lines(plan.get("setup")) or ["Confirm the test environment is ready."]
    interfaces = lines(plan.get("interfaces")) or ["Use the supported product interface."]
    output = [
        f"# {text(plan.get('title'), 'Product Playbook')}",
        "",
        text(plan.get("purpose"), "Run evidence-backed product journeys and record the results."),
        "",
        "## Test pass table",
        "",
        "| Pass | Use case | Scope | Estimated time |",
        "| --- | --- | --- | --- |",
        f"| Smoke | Fast confidence | {len(smoke)} scenarios | Approximate |",
        f"| Full | Complete covered journeys | {len(scenario_ids)} scenarios | Approximate |",
        "",
        "## Playbook map",
        "",
    ]
    output.extend(
        f"- [{chapter['title']}]({filename})"
        for chapter, filename in zip(chapters, files)
    )
    output.extend(
        [
            "- [Results template](results-template.md)",
            "",
            "## Actors and test data",
            "",
            "| Actor | Safe test data |",
            "| --- | --- |",
        ]
    )
    output.extend(f"| {actor} | Use approved disposable data. |" for actor in actors)
    output.extend(["", "## Before you start", ""])
    output.extend(f"{index}. {value}" for index, value in enumerate(setup, start=1))
    output.extend(["", "## Environment handoff", "", "Confirm environment-specific access with its owner.", ""])
    output.extend(["## Interface reference", ""])
    output.extend(f"- {value}" for value in interfaces)
    output.extend(
        [
            "",
            "## Run a scenario",
            "",
            "Follow every numbered step and confirm every expected result.",
            "",
            "## Capture a failure",
            "",
            "Record the scenario ID, observed result, environment, and useful evidence.",
            "",
            "## Severity guide",
            "",
            "- Blocker: The required journey cannot continue.",
            "- Major: A required outcome is wrong or unavailable.",
            "- Minor: The journey works with a limited defect.",
            "- Cosmetic: Presentation is affected without changing the outcome.",
            "",
            "## Smoke path",
            "",
        ]
    )
    output.extend(f"{index}. {scenario_id}" for index, scenario_id in enumerate(smoke, start=1))
    output.extend(["", "## Full pass", ""])
    output.extend(
        f"{index}. {scenario_id}" for index, scenario_id in enumerate(scenario_ids, start=1)
    )
    output.extend(
        [
            "",
            "## Sign-off",
            "",
            "Sign off after required scenarios pass or every exception is recorded.",
            "",
        ]
    )
    return "\n".join(output)


def render_results(chapters: list[dict[str, Any]]) -> str:
    output = [
        "# Results",
        "",
        "## Run details",
        "",
        "Record the date, environment, operator, and build or revision.",
        "",
        "## Environment coverage",
        "",
        "Record the browser, client, runtime, device, or environment used.",
        "",
        "## Actors",
        "",
        "Record the identities used without credentials or access links.",
        "",
        "## Test data",
        "",
        "Record the starting state, disposable data, and final cleanup state.",
        "",
        "## Legend",
        "",
        "Use P for Pass, F for Fail, B for Blocked, and N for N/A.",
        "",
    ]
    for chapter in chapters:
        output.extend(
            [
                f"### {chapter['title']}",
                "",
                "| ID | Result | Notes |",
                "| --- | --- | --- |",
            ]
        )
        output.extend(f"| {scenario['id']} | | |" for scenario in chapter["scenarios"])
        output.append("")
    output.extend(
        [
            "## Defects",
            "",
            "Record severity and evidence for every defect.",
            "",
            "## Blocked and N/A",
            "",
            "Explain every blocked or not-applicable result.",
            "",
            "## Cleanup",
            "",
            "Confirm changed data and temporary resources were cleaned up.",
            "",
            "## Summary",
            "",
            "Count each result and state the recommendation.",
            "",
            "## Sign-off",
            "",
            "Record the final decision and approver.",
            "",
        ]
    )
    return "\n".join(output)


def main() -> int:
    args = parse_args()
    try:
        plan = read_plan(Path(args.plan).expanduser().resolve())
        chapters = validate_plan(plan)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    output_dir = Path(args.output_dir).expanduser().resolve()
    existing = list(output_dir.glob("*.md")) if output_dir.is_dir() else []
    if existing and not args.force:
        raise SystemExit("destination already contains Markdown; reconcile it instead")
    output_dir.mkdir(parents=True, exist_ok=True)
    files = [
        f"{index:02d}-{slug(chapter['title'])}.md"
        for index, chapter in enumerate(chapters, start=1)
    ]
    (output_dir / "README.md").write_text(
        render_readme(plan, chapters, files),
        encoding="utf-8",
    )
    for index, (chapter, filename) in enumerate(zip(chapters, files)):
        next_target = files[index + 1] if index + 1 < len(files) else "results-template.md"
        (output_dir / filename).write_text(
            render_chapter(chapter, next_target),
            encoding="utf-8",
        )
    (output_dir / "results-template.md").write_text(
        render_results(chapters),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output_dir": str(output_dir),
                "chapters": len(chapters),
                "scenarios": sum(len(chapter["scenarios"]) for chapter in chapters),
                "files": ["README.md", *files, "results-template.md"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
