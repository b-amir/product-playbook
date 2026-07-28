#!/usr/bin/env python3
"""Validate a generated product manual-testing playbook."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import unquote


SCENARIO_HEADING = re.compile(
    r"^## ([A-Z][A-Z0-9]{1,5}-\d{2,3}):\s+(.+?)\s*$", re.MULTILINE
)
RESULT_ROW = re.compile(r"^\|\s*([A-Z][A-Z0-9]{1,5}-\d{2,3})\s*\|", re.MULTILINE)
RESULT_VALUE_ROW = re.compile(
    r"^\|\s*([A-Z][A-Z0-9]{1,5}-\d{2,3})\s*\|\s*([^|]*)\|",
    re.MULTILINE,
)
ANY_SCENARIO_ID = re.compile(r"\b[A-Z][A-Z0-9]{1,5}-\d{2,3}\b")
MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
FORBIDDEN_MARKERS = (
    "⚠️ NEEDS VERIFICATION",
    "NEEDS VERIFICATION",
    "PENDING VERIFICATION",
    "VERIFICATION REQUIRED",
    "UNRESOLVED",
    "SOURCED",
    "VERIFIED",
)
FORBIDDEN_SECTION_PATTERNS = (
    ("sources section", r"^#{1,6}\s+(sources?|source map)\s*$"),
    (
        "authoring provenance section",
        r"^#{1,6}\s+.*(evidence ledger|evidence status|authoring evidence|provenance|traceability).*$",
    ),
    (
        "verification metadata section",
        r"^#{1,6}\s+.*(verification (index|status|notes?|history|required|needed|gaps?)|"
        r"needs verification|pending verification).*$",
    ),
    (
        "reconciliation metadata section",
        r"^#{1,6}\s+.*reconciliation (summary|history|notes?|changes?).*$",
    ),
    (
        "authoring history section",
        r"^#{1,6}\s+.*((change|revision|update|authoring) history|"
        r"(change|revision|update|authoring) timeline|changelog).*$",
    ),
    (
        "unresolved authoring section",
        r"^#{1,6}\s+.*(known issues?|open issues?|open questions?|"
        r"unresolved items?|authoring gaps?|conflict log|todo|tbd).*$",
    ),
)
FORBIDDEN_PROSE_PATTERNS = (
    (
        "verification-needed note",
        r"\b(needs? verification|requires? verification|verification (pending|required|needed))\b",
    ),
    (
        "authoring timestamp",
        r"\b(last verified|generated (at|on|by)|reconciled (at|on|by)|"
        r"last updated (at|on|by))\b",
    ),
    (
        "authoring status",
        r"\b(evidence status|verification status|source status)\b",
    ),
    (
        "authoring history",
        r"\b(authoring history|change history|revision history|update history|"
        r"reconciliation history|changelog)\b",
    ),
    (
        "unresolved authoring note",
        r"\b(known issues?|open questions?|unresolved items?|authoring gaps?|todo|tbd)\b",
    ),
    (
        "inline provenance note",
        r"(^|\n)[ \t]*(source|evidence|provenance|traceability)[ \t]*:",
    ),
)
FORBIDDEN_FRONTMATTER_KEYS = {
    "authoring_history",
    "changelog",
    "evidence",
    "evidence_status",
    "generated_at",
    "generated_by",
    "history",
    "last_updated",
    "last_verified",
    "reconciliation",
    "sources",
    "status",
    "unresolved",
    "updated_at",
    "verification",
    "verification_status",
}
FORBIDDEN_STATE_KEYS = {
    "authoring_history",
    "changelog",
    "decisions",
    "generated_at",
    "history",
    "issues",
    "notes",
    "status",
    "timeline",
    "unresolved",
    "updated_at",
    "verification",
    "verification_status",
    "verified_at",
}
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
STATE_FILE_NAME = ".product-playbook-state.json"
LEGACY_STATE_DIR_NAME = ".product-playbook"
STATE_VERSION = 3


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a product-playbook output folder.")
    parser.add_argument("output_dir", help="Generated playbook directory")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable output")
    parser.add_argument(
        "--require-state",
        action="store_true",
        help="Require and validate portable collaboration state.",
    )
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
    if re.search(r"<!--.*?-->", text, re.DOTALL):
        issue(
            errors,
            "hidden-authoring-meta",
            "Published playbook must not contain hidden HTML comments",
            path,
        )
    for label, pattern in FORBIDDEN_SECTION_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE | re.MULTILINE):
            issue(
                errors,
                "forbidden-authoring-meta",
                f"Published playbook must not include a {label}",
                path,
            )
    prose = prose_only(text)
    for label, pattern in FORBIDDEN_PROSE_PATTERNS:
        if re.search(pattern, prose, re.IGNORECASE | re.MULTILINE):
            issue(
                errors,
                "forbidden-authoring-meta",
                f"Published playbook must not include a {label}",
                path,
            )
    frontmatter = re.match(r"^---[ \t]*\n(.*?)\n---[ \t]*(?:\n|\Z)", text, re.DOTALL)
    if frontmatter:
        keys = {
            match.group(1).lower()
            for match in re.finditer(
                r"^([A-Za-z0-9_-]+)\s*:",
                frontmatter.group(1),
                re.MULTILINE,
            )
        }
        leaked_keys = sorted(keys & FORBIDDEN_FRONTMATTER_KEYS)
        if leaked_keys:
            issue(
                errors,
                "forbidden-frontmatter",
                "Published playbook frontmatter contains authoring metadata: "
                + ", ".join(leaked_keys),
                path,
            )
    for marker in FORBIDDEN_MARKERS:
        if marker.lower() in prose.lower():
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
            if re.match(r"^(https?://|mailto:)", target):
                continue
            clean, _, anchor = target.partition("#")
            target_path = path if not clean else (path.parent / clean).resolve()
            if not target_path.exists():
                issue(errors, "broken-link", f"Broken relative link: {target}", path)
                continue
            if anchor and target_path.is_file() and target_path.suffix.lower() == ".md":
                headings = {
                    heading_slug(match.group(1))
                    for match in re.finditer(
                        r"^#{1,6}\s+(.+?)\s*$",
                        read(target_path),
                        re.MULTILINE,
                    )
                }
                if unquote(anchor).lower() not in headings:
                    issue(errors, "broken-anchor", f"Broken Markdown anchor: {target}", path)


def heading_slug(value: str) -> str:
    value = re.sub(r"[^\w\s-]", "", value.lower(), flags=re.UNICODE)
    return re.sub(r"[\s-]+", "-", value).strip("-")


def scenario_blocks(text: str) -> list[tuple[str, str]]:
    matches = list(SCENARIO_HEADING.finditer(text))
    blocks: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        blocks.append((match.group(1), text[match.end() : end]))
    return blocks


def section_body(text: str, heading_pattern: str) -> str:
    match = re.search(
        rf"^## {heading_pattern}[ \t]*$(.*?)(?=^## |\Z)",
        text,
        re.IGNORECASE | re.MULTILINE | re.DOTALL,
    )
    return match.group(1) if match else ""


def prose_only(text: str) -> str:
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    text = re.sub(r"`[^`\n]+`", "", text)
    text = re.sub(r"\*\*[^*\n]+\*\*", "", text)
    text = re.sub(r"https?://\S+", "", text)
    return text


def check_writing_contract(
    text: str,
    path: Path,
    errors: list[dict[str, str]],
) -> None:
    prose = prose_only(text)
    if "—" in prose:
        issue(errors, "forbidden-punctuation", "Prose contains an em dash", path)
    if ";" in prose:
        issue(errors, "forbidden-punctuation", "Prose contains a semicolon", path)


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
    check_writing_contract(text, path, errors)

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

    scenario_list_ids = set(
        RESULT_ROW.findall(section_body(text, r"scenario list[^\n]*"))
    )
    if scenario_list_ids != set(ids):
        issue(
            errors,
            "scenario-list-mismatch",
            "Scenario list IDs do not match chapter scenario headings",
            path,
        )
    checklist_ids = set(
        ANY_SCENARIO_ID.findall(section_body(text, r"chapter checklist[^\n]*"))
    )
    if checklist_ids != set(ids):
        issue(
            errors,
            "checklist-mismatch",
            "Chapter checklist IDs do not match chapter scenario headings",
            path,
        )
    return ids


def is_absolute_or_private_path(value: str) -> bool:
    return bool(
        value.startswith(("/", "~/"))
        or re.match(r"^[A-Za-z]:[\\/]", value)
        or "\\Users\\" in value
    )


def walk_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for child in value for item in walk_strings(child)]
    if isinstance(value, dict):
        return [item for child in value.values() for item in walk_strings(child)]
    return []


def walk_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return {
            *(str(key).lower() for key in value),
            *(key for child in value.values() for key in walk_keys(child)),
        }
    if isinstance(value, list):
        return {key for child in value for key in walk_keys(child)}
    return set()


def validate_state(
    root: Path,
    scenario_ids: set[str],
    errors: list[dict[str, str]],
) -> None:
    state_path = root / STATE_FILE_NAME
    if not state_path.is_file():
        issue(errors, "missing-state", f"Missing {STATE_FILE_NAME}")
        return
    try:
        state = json.loads(read(state_path))
    except json.JSONDecodeError:
        issue(errors, "invalid-state", "Collaboration state is not valid JSON", state_path)
        return
    if not isinstance(state, dict):
        issue(errors, "invalid-state", "Collaboration state must be a JSON object", state_path)
        return
    if state.get("schema_version") != STATE_VERSION:
        issue(errors, "invalid-state", "Unsupported state schema version", state_path)
    scenarios = state.get("scenarios")
    sources = state.get("sources")
    if not isinstance(scenarios, dict) or not isinstance(sources, dict):
        issue(
            errors,
            "invalid-state",
            "Collaboration state must contain sources and scenarios objects",
            state_path,
        )
        return
    state_ids = set(state.get("scenario_ids", []))
    if state_ids != scenario_ids:
        issue(
            errors,
            "state-scenario-mismatch",
            "State scenario IDs do not match the published playbook",
            state_path,
        )
    if state_ids != set(scenarios):
        issue(
            errors,
            "state-scenario-mismatch",
            "State scenario entries do not match the scenario ID list",
            state_path,
        )
    source_ids = set(state.get("source_ids", []))
    actual_source_ids = set(sources)
    if source_ids != actual_source_ids:
        issue(
            errors,
            "state-source-mismatch",
            "State source entries do not match the source ID list",
            state_path,
        )
    for scenario_id in sorted(scenario_ids):
        scenario_state = scenarios.get(scenario_id)
        if not isinstance(scenario_state, dict):
            issue(errors, "missing-state-scenario", f"Missing state for {scenario_id}")
            continue
        if not scenario_state.get("sources"):
            issue(
                errors,
                "missing-state-sources",
                f"State for {scenario_id} has no evidence",
                state_path,
            )
    expected_digest = state.get("state_digest")
    digest_input = {key: value for key, value in state.items() if key != "state_digest"}
    actual_digest = hashlib.sha256(
        json.dumps(
            digest_input,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    if expected_digest != actual_digest:
        issue(
            errors,
            "state-digest-mismatch",
            "Collaboration state digest does not match its contents",
            state_path,
        )
    if any(is_absolute_or_private_path(item) for item in walk_strings(state)):
        issue(
            errors,
            "nonportable-state",
            "Collaboration state contains a machine-specific path",
            state_path,
        )
    leaked_keys = sorted(walk_keys(state) & FORBIDDEN_STATE_KEYS)
    if leaked_keys:
        issue(
            errors,
            "authoring-meta-in-state",
            "Collaboration state contains authoring metadata: "
            + ", ".join(leaked_keys),
            state_path,
        )


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
        check_writing_contract(readme_text, readme, errors)
    if results.is_file():
        results_text = read(results)
        check_sections(results_text, RESULTS_SECTIONS, results, errors)
        check_forbidden_authoring_meta(results_text, results, errors)
        check_writing_contract(results_text, results, errors)

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
    if results.is_file():
        for scenario_id, result_value in RESULT_VALUE_ROW.findall(read(results)):
            if result_value.strip():
                issue(
                    errors,
                    "prepopulated-result",
                    f"Results template contains a prior result for {scenario_id}",
                    results,
                )

    if readme.is_file():
        known_ids = set(all_ids)
        map_targets = {
            target.split("#", 1)[0]
            for target in MARKDOWN_LINK.findall(
                section_body(read(readme), r"playbook map[^\n]*")
            )
            if not re.match(r"^(https?://|mailto:|#)", target)
        }
        expected_targets = {chapter.name for chapter in chapters}
        if not expected_targets <= map_targets:
            issue(
                errors,
                "playbook-map-mismatch",
                "Playbook map does not match chapters and results template",
                readme,
            )
        for label, pattern in (
            ("smoke path", r"smoke[^\n]*"),
            ("full pass", r"full pass[^\n]*"),
        ):
            referenced = set(ANY_SCENARIO_ID.findall(section_body(read(readme), pattern)))
            if not referenced:
                issue(
                    errors,
                    "empty-run-path",
                    f"{label} contains no scenario IDs",
                    readme,
                )
            unknown = sorted(referenced - known_ids)
            for scenario_id in unknown:
                issue(
                    errors,
                    "unknown-run-path-scenario",
                    f"{label} references unknown scenario {scenario_id}",
                    readme,
                )

    markdown_files = [path for path in root.rglob("*.md") if path.is_file()]
    check_links(root, markdown_files, errors)
    legacy_state_dir = root / LEGACY_STATE_DIR_NAME
    if legacy_state_dir.exists():
        issue(
            errors,
            "legacy-state-directory",
            (
                f"Legacy {LEGACY_STATE_DIR_NAME}/ state is not allowed; "
                f"migrate it to {STATE_FILE_NAME}"
            ),
            legacy_state_dir,
        )
    if args.require_state:
        validate_state(root, set(all_ids), errors)

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
