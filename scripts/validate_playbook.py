#!/usr/bin/env python3
"""Validate a generated product manual-testing playbook."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


SCENARIO_HEADING = re.compile(
    r"^## ([A-Z][A-Z0-9]{1,5}-\d{2,3}):\s+(.+?)\s*$", re.MULTILINE
)
RESULT_ROW = re.compile(r"^\|\s*([A-Z][A-Z0-9]{1,5}-\d{2,3})\s*\|", re.MULTILINE)
MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
FORBIDDEN_MARKERS = (
    "⚠️ NEEDS VERIFICATION",
    "NEEDS VERIFICATION",
)
FORBIDDEN_SECTION_PATTERNS = (
    ("sources section", r"^## Sources\s*$"),
    ("verification index", r"^## .*verification"),
    ("reconciliation summary", r"^## .*reconciliation"),
)
REQUIRED_SCENARIO_FIELDS = ("Goal", "Who", "Steps", "Expected")
README_SECTIONS = {
    "test-pass table": r"^## .*test pass",
    "playbook map": r"^## .*playbook map",
    "actors and data": r"^## .*(accounts|actors|identities).*(data|fixtures)",
    "before you start": r"^## .*before you start",
    "environment handoff": r"^## .*environment handoff",
    "interface reference": r"^## .*(route|address|interface|endpoint|command).*reference",
    "scenario instructions": r"^## .*run a scenario",
    "failure capture": r"^## .*capture.*fail",
    "severity guide": r"^## .*severity",
    "smoke path": r"^## .*smoke",
    "full pass": r"^## .*full pass",
    "sign-off": r"^## .*sign.?off",
}
RESULTS_SECTIONS = {
    "run details": r"^## .*run details",
    "environment coverage": r"^## .*(browser|client|runtime|environment).*coverage",
    "actors": r"^## .*(accounts|actors|identities)",
    "test data": r"^## .*test data",
    "legend": r"^## .*legend",
    "defects": r"^## .*defect",
    "blocked and N/A": r"^## .*(blocked|n/a)",
    "cleanup": r"^## .*cleanup",
    "summary": r"^## .*summary",
    "sign-off": r"^## .*sign.?off",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a product-playbook output folder.")
    parser.add_argument("output_dir", help="Generated playbook directory")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable output")
    return parser.parse_args()


def issue(
    collection: list[dict[str, str]], code: str, message: str, file: Path | None = None
) -> None:
    item = {"code": code, "message": message}
    if file is not None:
        item["file"] = file.name
    collection.append(item)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def check_sections(
    text: str,
    requirements: dict[str, str],
    path: Path,
    errors: list[dict[str, str]],
) -> None:
    for label, pattern in requirements.items():
        if not re.search(pattern, text, re.IGNORECASE | re.MULTILINE):
            issue(errors, "missing-section", f"Missing {label} section", path)


def check_forbidden_authoring_meta(
    text: str,
    path: Path,
    errors: list[dict[str, str]],
) -> None:
    for label, pattern in FORBIDDEN_SECTION_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE | re.MULTILINE):
            issue(
                errors,
                "forbidden-authoring-meta",
                f"Published playbook must not include a {label}",
                path,
            )
    for marker in FORBIDDEN_MARKERS:
        if marker in text:
            issue(
                errors,
                "forbidden-authoring-meta",
                f"Published playbook must not include `{marker}`",
                path,
            )
    if re.search(
        r"^\|\s*[A-Z][A-Z0-9]{1,5}-\d{2,3}\s*\|\s*(VERIFIED|SOURCED|NEEDS VERIFICATION)\s*\|",
        text,
        re.MULTILINE,
    ):
        issue(
            errors,
            "forbidden-authoring-meta",
            "Published playbook must not include evidence-status tables",
            path,
        )


def check_links(
    root: Path,
    files: list[Path],
    errors: list[dict[str, str]],
) -> None:
    for path in files:
        for target in MARKDOWN_LINK.findall(read(path)):
            if re.match(r"^(https?://|mailto:|#)", target):
                continue
            clean = target.split("#", 1)[0]
            if not clean:
                continue
            if not (path.parent / clean).resolve().exists():
                issue(errors, "broken-link", f"Broken relative link: {target}", path)


def scenario_blocks(text: str) -> list[tuple[str, str]]:
    matches = list(SCENARIO_HEADING.finditer(text))
    blocks: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        blocks.append((match.group(1), text[match.end() : end]))
    return blocks


def validate_chapter(
    path: Path,
    errors: list[dict[str, str]],
    warnings: list[dict[str, str]],
) -> list[str]:
    text = read(path)
    ids: list[str] = []

    if not re.search(r"^## .*scenario list", text, re.IGNORECASE | re.MULTILINE):
        issue(errors, "missing-scenario-list", "Missing scenario list", path)
    if not re.search(r"^## .*chapter checklist", text, re.IGNORECASE | re.MULTILINE):
        issue(errors, "missing-checklist", "Missing chapter checklist", path)

    check_forbidden_authoring_meta(text, path, errors)

    for scenario_id, block in scenario_blocks(text):
        ids.append(scenario_id)
        for field in REQUIRED_SCENARIO_FIELDS:
            if not re.search(rf"^\*\*{re.escape(field)}\*\*\s*$", block, re.MULTILINE):
                issue(
                    errors,
                    "missing-scenario-field",
                    f"{scenario_id} is missing {field}",
                    path,
                )
        steps = re.search(
            r"^\*\*Steps\*\*\s*(.*?)(?=^\*\*[A-Z][^*]*\*\*\s*$|\Z)",
            block,
            re.MULTILINE | re.DOTALL,
        )
        if steps and not re.search(r"^\d+\.\s+", steps.group(1), re.MULTILINE):
            issue(errors, "missing-numbered-step", f"{scenario_id} has no numbered step", path)
        expected = re.search(
            r"^\*\*Expected\*\*\s*(.*?)(?=^\*\*[A-Z][^*]*\*\*\s*$|\Z)",
            block,
            re.MULTILINE | re.DOTALL,
        )
        if expected and not re.search(r"^-\s+", expected.group(1), re.MULTILINE):
            issue(
                errors,
                "missing-expected-bullet",
                f"{scenario_id} has no expected-result bullet",
                path,
            )

    if not re.search(r"\]\([^)]+\.md(?:#[^)]+)?\)", text):
        issue(warnings, "missing-next-link", "No next-document link found", path)
    return ids


def main() -> int:
    args = parse_args()
    root = Path(args.output_dir).expanduser().resolve()
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    if not root.is_dir():
        raise SystemExit(f"playbook directory is not a directory: {root}")

    readme = root / "README.md"
    results = root / "results-template.md"
    chapters = sorted(
        path
        for path in root.glob("[0-9][0-9]-*.md")
        if path.name not in {"README.md", "results-template.md"}
    )
    if not readme.is_file():
        issue(errors, "missing-file", "Missing README.md")
    if not results.is_file():
        issue(errors, "missing-file", "Missing results-template.md")
    if not chapters:
        issue(errors, "missing-chapters", "No numbered chapter files found")

    if readme.is_file():
        readme_text = read(readme)
        check_sections(readme_text, README_SECTIONS, readme, errors)
        check_forbidden_authoring_meta(readme_text, readme, errors)
    if results.is_file():
        results_text = read(results)
        check_sections(results_text, RESULTS_SECTIONS, results, errors)
        check_forbidden_authoring_meta(results_text, results, errors)

    all_ids: list[str] = []
    for chapter in chapters:
        chapter_ids = validate_chapter(chapter, errors, warnings)
        all_ids.extend(chapter_ids)

    duplicates = sorted(item for item, count in Counter(all_ids).items() if count > 1)
    for scenario_id in duplicates:
        issue(errors, "duplicate-scenario", f"Duplicate scenario ID {scenario_id}")

    result_ids = RESULT_ROW.findall(read(results)) if results.is_file() else []
    result_counts = Counter(result_ids)
    for scenario_id, count in sorted(result_counts.items()):
        if count > 1:
            issue(errors, "duplicate-result-row", f"Results template repeats {scenario_id}")
    for scenario_id in sorted(set(all_ids) - set(result_ids)):
        issue(errors, "missing-result-row", f"Results template is missing {scenario_id}")
    for scenario_id in sorted(set(result_ids) - set(all_ids)):
        issue(errors, "extra-result-row", f"Results template contains unknown {scenario_id}")

    markdown_files = [path for path in root.rglob("*.md") if path.is_file()]
    check_links(root, markdown_files, errors)

    report: dict[str, Any] = {
        "valid": not errors,
        "files": len(markdown_files),
        "chapters": len(chapters),
        "scenarios": len(all_ids),
        "errors": errors,
        "warnings": warnings,
    }

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        label = "PASS" if not errors else "FAIL"
        print(
            f"{label}: {len(chapters)} chapters, {len(all_ids)} scenarios, "
            f"{len(errors)} errors, {len(warnings)} warnings"
        )
        for item in errors:
            location = f" ({item['file']})" if "file" in item else ""
            print(f"ERROR [{item['code']}]{location}: {item['message']}")
        for item in warnings:
            location = f" ({item['file']})" if "file" in item else ""
            print(f"WARN [{item['code']}]{location}: {item['message']}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
