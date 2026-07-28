#!/usr/bin/env python3
"""Inventory an existing playbook and maintain evidence fingerprints for safe reuse."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STATE_NAME = ".product-playbook-state.json"
STATE_VERSION = 1
SKIP_DIRS = {
    ".git",
    ".next",
    ".nuxt",
    ".output",
    ".pytest_cache",
    ".react-router",
    ".svelte-kit",
    ".venv",
    "__pycache__",
    "artifacts",
    "build",
    "coverage",
    "dist",
    "generated",
    "node_modules",
    "out",
    "playwright-report",
    "target",
    "test-results",
    "vendor",
}
EVIDENCE_SUFFIXES = {
    ".adoc",
    ".cjs",
    ".cs",
    ".dart",
    ".go",
    ".gql",
    ".graphql",
    ".java",
    ".js",
    ".jsx",
    ".kt",
    ".md",
    ".mdx",
    ".mjs",
    ".php",
    ".proto",
    ".py",
    ".raml",
    ".rb",
    ".rs",
    ".rst",
    ".scala",
    ".swift",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}
MANIFEST_NAMES = {
    "Cargo.toml",
    "Gemfile",
    "build.gradle",
    "build.gradle.kts",
    "composer.json",
    "go.mod",
    "package.json",
    "pom.xml",
    "pyproject.toml",
    "requirements-dev.txt",
    "requirements.txt",
    "setup.cfg",
    "tox.ini",
}
SCENARIO_HEADING = re.compile(
    r"^## ([A-Z][A-Z0-9]{1,5}-\d{2,3}):\s+(.+?)\s*$", re.MULTILINE
)
SOURCE_ROW = re.compile(
    r"^\|\s*([A-Z][A-Z0-9]{1,5}-\d{2,3})\s*\|\s*"
    r"(VERIFIED|SOURCED|NEEDS VERIFICATION)\s*\|(.*)$",
    re.MULTILINE,
)
BACKTICK = re.compile(r"`([^`]+)`")
MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a compact draft inventory and check or write evidence state."
    )
    parser.add_argument("draft_path", help="Existing playbook directory")
    parser.add_argument(
        "--code-repo",
        action="append",
        default=[],
        help="Code repository root. Repeat when needed.",
    )
    parser.add_argument(
        "--docs-path",
        action="append",
        default=[],
        help="Documentation root. Repeat when needed.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--write-state",
        action="store_true",
        help=f"Write {STATE_NAME} after a validated generation.",
    )
    mode.add_argument(
        "--check-state",
        action="store_true",
        help="Compare the current sources with the saved state.",
    )
    parser.add_argument("--output", help="Write JSON report to this file")
    return parser.parse_args()


def read(path: Path, limit: int = 1_000_000) -> str:
    try:
        if path.stat().st_size > limit:
            return ""
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(131_072), b""):
                digest.update(chunk)
    except OSError:
        return ""
    return digest.hexdigest()


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def walk_evidence_files(root: Path, excluded: Path | None = None) -> list[Path]:
    files: list[Path] = []
    for current, dirs, names in os.walk(root):
        base = Path(current)
        dirs[:] = sorted(
            directory
            for directory in dirs
            if directory not in SKIP_DIRS
            and not directory.startswith(".cache")
            and (excluded is None or (base / directory).resolve() != excluded)
        )
        for name in sorted(names):
            path = base / name
            if (
                path.suffix.lower() in EVIDENCE_SUFFIXES
                or path.name in MANIFEST_NAMES
                or path.suffix.lower() == ".csproj"
            ):
                files.append(path)
    return files


def root_fingerprint(root: Path, excluded: Path | None = None) -> dict[str, Any]:
    digest = hashlib.sha256()
    count = 0
    for path in walk_evidence_files(root, excluded):
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            continue
        file_hash = hash_file(path)
        if not file_hash:
            continue
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_hash.encode("ascii"))
        digest.update(b"\0")
        count += 1
    return {"digest": digest.hexdigest(), "file_count": count}


def git_metadata(root: Path) -> dict[str, Any]:
    def run(*args: str) -> str:
        try:
            result = subprocess.run(
                ["git", "-C", str(root), *args],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired):
            return ""
        return result.stdout.strip() if result.returncode == 0 else ""

    commit = run("rev-parse", "HEAD")
    status = run("status", "--porcelain")
    return {
        "commit": commit or None,
        "dirty": bool(status),
    }


def scenario_blocks(text: str) -> list[dict[str, str]]:
    matches = list(SCENARIO_HEADING.finditer(text))
    blocks: list[dict[str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.end() : end]
        blocks.append(
            {
                "id": match.group(1),
                "title": match.group(2),
                "body_hash": hash_text(body),
            }
        )
    return blocks


def clean_reference(raw: str) -> str:
    value = raw.strip()
    value = re.sub(r":\d+(?::\d+)?$", "", value)
    value = value.split("#", 1)[0]
    return value.strip()


def resolve_reference(
    raw: str,
    roots: list[tuple[str, Path]],
    preferred_kind: str,
) -> dict[str, Any] | None:
    cleaned = clean_reference(raw)
    if not cleaned or cleaned.lower() in {"none", "n/a"}:
        return None
    path = Path(cleaned)
    if path.is_absolute() and path.is_file():
        for label, root in roots:
            try:
                relative_path = path.relative_to(root)
            except ValueError:
                continue
            return {
                "root": label,
                "path": relative_path.as_posix(),
                "sha256": hash_file(path),
            }
        return None
    ordered = sorted(roots, key=lambda item: item[0].startswith(preferred_kind), reverse=True)
    for label, root in ordered:
        candidate = (root / cleaned).resolve()
        if candidate.is_file():
            return {
                "root": label,
                "path": cleaned,
                "sha256": hash_file(candidate),
            }
    return None


def parse_source_maps(
    markdown_files: list[Path],
    roots: list[tuple[str, Path]],
) -> dict[str, dict[str, Any]]:
    scenarios: dict[str, dict[str, Any]] = {}
    for path in markdown_files:
        text = read(path)
        for match in SOURCE_ROW.finditer(text):
            scenario_id = match.group(1)
            status = match.group(2)
            remaining = match.group(3)
            cells = [cell.strip() for cell in remaining.split("|")]
            code_cells = cells[:2]
            docs_cells = cells[2:3]
            references: list[dict[str, Any]] = []
            unresolved: list[str] = []
            for cell in code_cells:
                for raw in BACKTICK.findall(cell):
                    resolved = resolve_reference(raw, roots, "code")
                    if resolved:
                        references.append(resolved)
                    elif "/" in raw or "." in Path(clean_reference(raw)).name:
                        unresolved.append(raw)
            for cell in docs_cells:
                for raw in BACKTICK.findall(cell):
                    resolved = resolve_reference(raw, roots, "docs")
                    if resolved:
                        references.append(resolved)
                    elif "/" in raw or "." in Path(clean_reference(raw)).name:
                        unresolved.append(raw)
            scenarios[scenario_id] = {
                "status": status,
                "sources": references,
                "unresolved_source_refs": sorted(set(unresolved)),
            }
    return scenarios


def broken_links(markdown_files: list[Path]) -> list[str]:
    broken: list[str] = []
    for path in markdown_files:
        for target in MARKDOWN_LINK.findall(read(path)):
            if re.match(r"^(https?://|mailto:|#)", target):
                continue
            clean = target.split("#", 1)[0]
            if clean and not (path.parent / clean).resolve().exists():
                broken.append(f"{path.name}:{target}")
    return sorted(set(broken))


def inventory(
    draft: Path,
    code_roots: list[Path],
    docs_roots: list[Path],
) -> dict[str, Any]:
    markdown = sorted(path for path in draft.glob("*.md") if path.is_file())
    roots = [
        *((f"code{index}", root) for index, root in enumerate(code_roots)),
        *((f"docs{index}", root) for index, root in enumerate(docs_roots)),
    ]
    blocks = [
        {**scenario, "file": path.name}
        for path in markdown
        for scenario in scenario_blocks(read(path))
    ]
    source_maps = parse_source_maps(markdown, roots)
    for scenario in blocks:
        scenario.update(source_maps.get(scenario["id"], {}))
    combined = "\n".join(read(path) for path in markdown)
    return {
        "draft_path": str(draft),
        "markdown_files": [path.name for path in markdown],
        "scenario_count": len(blocks),
        "scenarios": blocks,
        "broken_links": broken_links(markdown),
        "needs_verification_markers": combined.count("⚠️ NEEDS VERIFICATION")
        + combined.count("## Sources")
        + len(re.findall(r"^## .*verification", combined, re.I | re.M)),
        "draft_digest": hash_text(combined),
    }


def current_roots(
    draft: Path,
    code_roots: list[Path],
    docs_roots: list[Path],
) -> dict[str, dict[str, Any]]:
    entries: dict[str, dict[str, Any]] = {}
    for kind, roots in (("code", code_roots), ("docs", docs_roots)):
        for index, root in enumerate(roots):
            label = f"{kind}{index}"
            excluded = draft if draft == root or draft.is_relative_to(root) else None
            entries[label] = {
                "fingerprint": root_fingerprint(root, excluded),
                "git": git_metadata(root),
            }
    return entries


def build_state(
    draft: Path,
    draft_inventory: dict[str, Any],
    roots: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": STATE_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "draft_digest": draft_inventory["draft_digest"],
        "roots": roots,
        "scenarios": {
            scenario["id"]: {
                "title": scenario["title"],
                "status": scenario.get("status", "SOURCED"),
                "body_hash": scenario["body_hash"],
                "sources": scenario.get("sources", []),
            }
            for scenario in draft_inventory["scenarios"]
        },
    }


def compare_state(
    state: dict[str, Any],
    draft_inventory: dict[str, Any],
    roots: dict[str, dict[str, Any]],
    code_roots: list[Path],
    docs_roots: list[Path],
) -> dict[str, Any]:
    if state.get("schema_version") != STATE_VERSION:
        return {
            "full_audit_required": True,
            "reason": "state schema is missing or unsupported",
        }
    root_paths = {
        **{f"code{index}": root for index, root in enumerate(code_roots)},
        **{f"docs{index}": root for index, root in enumerate(docs_roots)},
    }
    previous_roots = state.get("roots", {})
    previous_scenarios = state.get("scenarios", {})
    changed_roots = sorted(
        label
        for label, current in roots.items()
        if previous_roots.get(label, {}).get("fingerprint", {}).get("digest")
        != current.get("fingerprint", {}).get("digest")
    )
    impacted: set[str] = set()
    missing_sources: dict[str, list[str]] = {}
    for scenario_id, scenario in previous_scenarios.items():
        for source in scenario.get("sources", []):
            label = source.get("root")
            source_path = source.get("path")
            root = root_paths.get(label)
            if not root or not source_path:
                impacted.add(scenario_id)
                continue
            candidate = (root / source_path).resolve()
            current_hash = hash_file(candidate) if candidate.is_file() else ""
            if current_hash != source.get("sha256"):
                impacted.add(scenario_id)
                if not current_hash:
                    missing_sources.setdefault(scenario_id, []).append(source_path)

    edited_scenarios = sorted(
        scenario["id"]
        for scenario in draft_inventory["scenarios"]
        if scenario["id"] in previous_scenarios
        and scenario["body_hash"]
        != previous_scenarios[scenario["id"]].get("body_hash")
    )
    impacted.update(edited_scenarios)
    current_ids = {scenario["id"] for scenario in draft_inventory["scenarios"]}
    previous_ids = set(previous_scenarios)
    draft_changed = state.get("draft_digest") != draft_inventory["draft_digest"]
    scenarios_without_sources = sorted(
        scenario["id"]
        for scenario in draft_inventory["scenarios"]
        if not scenario.get("sources")
    )
    full_audit = bool(
        not previous_ids
        or current_ids != previous_ids
        or draft_inventory["broken_links"]
    )
    reusable = sorted(
        scenario_id
        for scenario_id in current_ids
        if scenario_id not in impacted
        and scenario_id not in scenarios_without_sources
        and scenario_id in previous_ids
    )
    return {
        "full_audit_required": full_audit,
        "coverage_scan_required": bool(changed_roots),
        "draft_review_required": draft_changed,
        "changed_roots": changed_roots,
        "edited_scenarios": edited_scenarios,
        "impacted_scenarios": sorted(impacted),
        "reusable_scenarios": reusable,
        "scenarios_without_sources": scenarios_without_sources,
        "missing_sources": missing_sources,
        "added_scenarios": sorted(current_ids - previous_ids),
        "removed_scenarios": sorted(previous_ids - current_ids),
    }


def main() -> int:
    args = parse_args()
    draft = Path(args.draft_path).expanduser().resolve()
    if not draft.is_dir():
        raise SystemExit(f"draft path is not a directory: {draft}")
    code_roots = [Path(raw).expanduser().resolve() for raw in args.code_repo]
    docs_roots = [Path(raw).expanduser().resolve() for raw in args.docs_path]
    for root in [*code_roots, *docs_roots]:
        if not root.exists():
            raise SystemExit(f"source root does not exist: {root}")

    report = inventory(draft, code_roots, docs_roots)
    roots = current_roots(draft, code_roots, docs_roots)
    state_path = draft / STATE_NAME
    report["state_path"] = str(state_path)
    report["state_found"] = state_path.is_file()

    if args.check_state:
        if not state_path.is_file():
            report["incremental"] = {
                "full_audit_required": True,
                "coverage_scan_required": True,
                "reason": "no saved evidence state exists",
                "impacted_scenarios": [
                    scenario["id"] for scenario in report["scenarios"]
                ],
                "reusable_scenarios": [],
            }
        else:
            try:
                state = json.loads(read(state_path))
            except json.JSONDecodeError:
                state = {}
            report["incremental"] = compare_state(
                state, report, roots, code_roots, docs_roots
            )

    if args.write_state:
        state = build_state(draft, report, roots)
        state_path.write_text(
            json.dumps(state, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        report["state_found"] = True
        report["state_written"] = True

    output = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        Path(args.output).expanduser().write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
