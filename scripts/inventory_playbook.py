#!/usr/bin/env python3
"""Inventory an existing playbook and maintain evidence fingerprints for safe reuse."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from source_utils import SourceSpec, ensure_unique_sources, legacy_specs, parse_source_spec


STATE_FILE_NAME = ".product-playbook-state.json"
STATE_MANAGED_BY = "product-playbook"
LEGACY_STATE_DIR_NAME = ".product-playbook"
LEGACY_MANIFEST_NAME = "manifest.json"
STATE_VERSION = 3
LEGACY_STATE_VERSION = 2
LEGACY_MONOLITHIC_STATE_VERSION = 1
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
    ".bats",
    ".cjs",
    ".cs",
    ".dart",
    ".ex",
    ".exs",
    ".go",
    ".gql",
    ".graphql",
    ".java",
    ".js",
    ".jsx",
    ".json",
    ".kt",
    ".lua",
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
    ".sh",
    ".swift",
    ".sql",
    ".ts",
    ".tsx",
    ".txt",
    ".toml",
    ".xml",
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
    "mix.exs",
    "package.json",
    "Package.swift",
    "pom.xml",
    "pubspec.yaml",
    "pyproject.toml",
    "requirements-dev.txt",
    "requirements.txt",
    "setup.cfg",
    "tox.ini",
}
SCENARIO_HEADING = re.compile(
    r"^## ([A-Z][A-Z0-9]{1,5}-\d{2,3}):\s+(.+?)\s*$", re.MULTILINE
)
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
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        metavar="SOURCE_ID=PATH",
        help="Portable code source mapping. Repeat when needed.",
    )
    parser.add_argument(
        "--docs-source",
        action="append",
        default=[],
        metavar="SOURCE_ID=PATH",
        help="Portable documentation source mapping. Repeat when needed.",
    )
    parser.add_argument(
        "--scope",
        action="append",
        default=[],
        metavar="SOURCE_ID",
        help="Source accessible during this contribution. Repeat when needed.",
    )
    parser.add_argument(
        "--run-scope",
        choices=("full", "contribution", "audit"),
        default="full",
        help="Full reconciliation, scoped contribution, or read-only audit.",
    )
    parser.add_argument(
        "--evidence-ledger",
        help="Internal JSON ledger used to write portable per-scenario evidence state.",
    )
    parser.add_argument(
        "--base-state-digest",
        help="Expected digest from the state read before editing. Reject stale writes.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--write-state",
        action="store_true",
        help=f"Write portable state to {STATE_FILE_NAME} after validation.",
    )
    mode.add_argument(
        "--check-state",
        action="store_true",
        help="Compare the current sources with the saved state.",
    )
    mode.add_argument(
        "--migrate-state",
        action="store_true",
        help=(
            f"Consolidate legacy {LEGACY_STATE_DIR_NAME}/ state into "
            f"{STATE_FILE_NAME} and remove the recognized legacy files."
        ),
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
    if (root / ".git").exists():
        try:
            result = subprocess.run(
                [
                    "git",
                    "-C",
                    str(root),
                    "ls-files",
                    "--cached",
                    "--others",
                    "--exclude-standard",
                    "-z",
                ],
                check=False,
                capture_output=True,
                timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired):
            result = None
        if result is not None and result.returncode == 0:
            files: list[Path] = []
            for raw in result.stdout.split(b"\0"):
                if not raw:
                    continue
                path = root / Path(raw.decode("utf-8", errors="replace"))
                if excluded and (path == excluded or path.is_relative_to(excluded)):
                    continue
                if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
                    continue
                if (
                    path.suffix.lower() in EVIDENCE_SUFFIXES
                    or path.name in MANIFEST_NAMES
                    or path.suffix.lower() == ".csproj"
                ) and path.is_file():
                    files.append(path)
            return sorted(files)

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


def inventory(draft: Path) -> dict[str, Any]:
    markdown = sorted(path for path in draft.glob("*.md") if path.is_file())
    blocks = [
        {**scenario, "file": path.name}
        for path in markdown
        for scenario in scenario_blocks(read(path))
    ]
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


def collect_sources(args: argparse.Namespace) -> list[SourceSpec]:
    specs = [
        *(parse_source_spec(raw, "code") for raw in args.source),
        *(parse_source_spec(raw, "docs") for raw in args.docs_source),
        *legacy_specs(args.code_repo, args.docs_path),
    ]
    ensure_unique_sources(specs)
    for spec in specs:
        root = Path(spec.locator).expanduser().resolve()
        if not root.is_dir():
            raise ValueError(f"source is not a directory: {spec.source_id}")
    return specs


def source_roots(specs: list[SourceSpec]) -> dict[str, Path]:
    return {
        spec.source_id: Path(spec.locator).expanduser().resolve()
        for spec in specs
    }


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(read(path))
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def legacy_state_paths(draft: Path) -> tuple[Path, Path, Path]:
    state_dir = draft / LEGACY_STATE_DIR_NAME
    return state_dir, state_dir / "sources", state_dir / "scenarios"


def empty_state() -> dict[str, Any]:
    return {
        "manifest": {},
        "sources": {},
        "scenarios": {},
        "format": None,
    }


def load_unified_state(draft: Path) -> dict[str, Any]:
    value = read_json(draft / STATE_FILE_NAME)
    if not value:
        return empty_state()
    sources = value.get("sources")
    scenarios = value.get("scenarios")
    if not isinstance(sources, dict) or not isinstance(scenarios, dict):
        return empty_state()
    manifest = {
        key: item
        for key, item in value.items()
        if key not in {"sources", "scenarios"}
    }
    return {
        "manifest": manifest,
        "sources": sources,
        "scenarios": scenarios,
        "format": "unified",
    }


def load_legacy_state(draft: Path) -> dict[str, Any]:
    state_dir, sources_dir, scenarios_dir = legacy_state_paths(draft)
    manifest = read_json(state_dir / LEGACY_MANIFEST_NAME)
    if not manifest:
        return empty_state()
    sources = {
        path.stem: read_json(path)
        for path in sorted(sources_dir.glob("*.json"))
        if path.is_file()
    }
    scenarios = {
        path.stem: read_json(path)
        for path in sorted(scenarios_dir.glob("*.json"))
        if path.is_file()
    }
    return {
        "manifest": manifest,
        "sources": sources,
        "scenarios": scenarios,
        "format": "legacy",
    }


def load_structured_state(draft: Path) -> dict[str, Any]:
    unified = load_unified_state(draft)
    return unified if unified["manifest"] else load_legacy_state(draft)


def build_unified_state(
    draft_inventory: dict[str, Any],
    run_scope: str,
    source_state: dict[str, Any],
    scenario_state: dict[str, Any],
) -> dict[str, Any]:
    core = {
        "managed_by": STATE_MANAGED_BY,
        "schema_version": STATE_VERSION,
        "draft_digest": draft_inventory["draft_digest"],
        "run_scope": run_scope,
        "source_ids": sorted(source_state),
        "scenario_ids": sorted(scenario_state),
        "sources": source_state,
        "scenarios": scenario_state,
    }
    state_digest = hash_text(
        json.dumps(core, sort_keys=True, separators=(",", ":"))
    )
    return {**core, "state_digest": state_digest}


def validate_legacy_layout(draft: Path) -> list[Path]:
    state_dir, sources_dir, scenarios_dir = legacy_state_paths(draft)
    if not state_dir.exists():
        return []
    if state_dir.is_symlink() or not state_dir.is_dir():
        raise ValueError(f"legacy state path is not a directory: {state_dir}")
    allowed_directories = {sources_dir, scenarios_dir}
    owned_files: list[Path] = []
    for path in state_dir.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"legacy state contains a symbolic link: {path.name}")
        if path.is_dir():
            if path not in allowed_directories:
                raise ValueError(
                    "legacy state contains an unexpected directory; refusing cleanup: "
                    + path.relative_to(state_dir).as_posix()
                )
            continue
        relative = path.relative_to(state_dir)
        is_manifest = relative == Path(LEGACY_MANIFEST_NAME)
        is_owned_entry = (
            len(relative.parts) == 2
            and relative.parts[0] in {"sources", "scenarios"}
            and path.suffix == ".json"
        )
        if not (is_manifest or is_owned_entry):
            raise ValueError(
                "legacy state contains an unexpected file; refusing cleanup: "
                + relative.as_posix()
            )
        owned_files.append(path)
    return owned_files


def cleanup_legacy_state(draft: Path) -> None:
    state_dir, sources_dir, scenarios_dir = legacy_state_paths(draft)
    owned_files = validate_legacy_layout(draft)
    for path in owned_files:
        path.unlink()
    for directory in (sources_dir, scenarios_dir):
        if directory.exists():
            directory.rmdir()
    if state_dir.exists():
        state_dir.rmdir()


def migrate_legacy_state(draft: Path) -> dict[str, Any]:
    legacy = load_legacy_state(draft)
    manifest = legacy["manifest"]
    if manifest.get("schema_version") != LEGACY_STATE_VERSION:
        raise ValueError("legacy collaboration state is missing or unsupported")
    existing_path = draft / STATE_FILE_NAME
    if existing_path.exists():
        existing = read_json(existing_path)
        allowed_keys = {
            "schema_version",
            "generated_at",
            "draft_digest",
            "roots",
            "scenarios",
        }
        existing_scenarios = existing.get("scenarios")
        if (
            existing.get("schema_version") != LEGACY_MONOLITHIC_STATE_VERSION
            or not isinstance(existing_scenarios, dict)
            or not set(existing) <= allowed_keys
            or set(existing_scenarios) != set(legacy["scenarios"])
        ):
            raise ValueError(
                f"{STATE_FILE_NAME} already exists and is not a matching legacy "
                "schema-1 state file; refusing to overwrite it"
            )
    validate_legacy_layout(draft)
    draft_inventory = inventory(draft)
    unified = build_unified_state(
        draft_inventory,
        str(manifest.get("run_scope", "full")),
        legacy["sources"],
        legacy["scenarios"],
    )
    write_json(draft / STATE_FILE_NAME, unified)
    cleanup_legacy_state(draft)
    return unified


def load_evidence_ledger(path: str | None) -> dict[str, Any]:
    if not path:
        raise ValueError("--evidence-ledger is required with --write-state")
    ledger_path = Path(path).expanduser().resolve()
    if not ledger_path.is_file():
        raise ValueError("evidence ledger is not a file")
    ledger = read_json(ledger_path)
    scenarios = ledger.get("scenarios")
    if not isinstance(scenarios, dict):
        raise ValueError("evidence ledger must contain a scenarios object")
    return ledger


def safe_source_reference(
    source_id: str,
    raw_path: str,
    roots: dict[str, Path],
) -> dict[str, str]:
    root = roots.get(source_id)
    if root is None:
        raise ValueError(f"evidence names inaccessible source: {source_id}")
    candidate_path = Path(raw_path)
    if candidate_path.is_absolute() or ".." in candidate_path.parts:
        raise ValueError("evidence paths must be source-relative and contained by their source")
    candidate = (root / candidate_path).resolve()
    try:
        relative_path = candidate.relative_to(root)
    except ValueError as error:
        raise ValueError("evidence path escapes its source root") from error
    if not candidate.is_file():
        raise ValueError(f"evidence file does not exist: {source_id}:{raw_path}")
    return {
        "source_id": source_id,
        "path": relative_path.as_posix(),
        "sha256": hash_file(candidate),
    }


def normalize_ledger_scenario(
    scenario_id: str,
    entry: Any,
    roots: dict[str, Path],
    allowed_sources: set[str],
) -> dict[str, Any]:
    if not isinstance(entry, dict):
        raise ValueError(f"ledger scenario {scenario_id} must be an object")
    status = entry.get("status", "SOURCED")
    if status not in {"SOURCED", "VERIFIED"}:
        raise ValueError(
            f"ledger scenario {scenario_id} must be SOURCED or VERIFIED before publication"
        )
    raw_sources = entry.get("sources")
    if not isinstance(raw_sources, list) or not raw_sources:
        raise ValueError(f"ledger scenario {scenario_id} must cite at least one source")
    sources: list[dict[str, str]] = []
    for raw in raw_sources:
        if not isinstance(raw, dict):
            raise ValueError(f"ledger scenario {scenario_id} has an invalid source")
        source_id = str(raw.get("source_id", ""))
        path = str(raw.get("path", ""))
        if source_id not in allowed_sources:
            raise ValueError(
                f"ledger scenario {scenario_id} cites source outside this run scope: {source_id}"
            )
        sources.append(safe_source_reference(source_id, path, roots))
    return {
        "sources": sorted(sources, key=lambda item: (item["source_id"], item["path"])),
    }


def structured_compare(
    draft_inventory: dict[str, Any],
    state: dict[str, Any],
    roots: dict[str, Path],
) -> dict[str, Any]:
    manifest = state["manifest"]
    previous_scenarios = state["scenarios"]
    draft = Path(draft_inventory["draft_path"]).resolve()
    if manifest.get("schema_version") not in {
        STATE_VERSION,
        LEGACY_STATE_VERSION,
    }:
        return {
            "full_audit_required": True,
            "coverage_scan_required": True,
            "reason": "portable collaboration state is missing or unsupported",
            "impacted_scenarios": [
                scenario["id"] for scenario in draft_inventory["scenarios"]
            ],
            "reusable_scenarios": [],
        }

    current_by_id = {
        scenario["id"]: scenario for scenario in draft_inventory["scenarios"]
    }
    impacted: set[str] = set()
    changed_sources: set[str] = set()
    for source_id, root in roots.items():
        prior = state["sources"].get(source_id, {})
        current_git = git_metadata(root)
        if (
            prior.get("revision")
            and prior.get("revision") == current_git.get("commit")
            and not prior.get("dirty")
            and not current_git.get("dirty")
        ):
            current = prior.get("fingerprint", {})
        else:
            current = root_fingerprint(
                root,
                draft if draft == root or draft.is_relative_to(root) else None,
            )
        if prior.get("fingerprint", {}).get("digest") != current.get("digest"):
            changed_sources.add(source_id)

    missing_sources: dict[str, list[str]] = {}
    preserved_out_of_scope: list[str] = []
    for scenario_id, prior in previous_scenarios.items():
        current = current_by_id.get(scenario_id)
        if current and current["body_hash"] != prior.get("body_hash"):
            impacted.add(scenario_id)
        for source in prior.get("sources", []):
            source_id = source.get("source_id")
            path = source.get("path")
            root = roots.get(source_id)
            if root is None:
                preserved_out_of_scope.append(scenario_id)
                continue
            candidate = (root / str(path)).resolve()
            current_hash = hash_file(candidate) if candidate.is_file() else ""
            if current_hash != source.get("sha256"):
                impacted.add(scenario_id)
                if not current_hash:
                    missing_sources.setdefault(scenario_id, []).append(str(path))

    current_ids = set(current_by_id)
    previous_ids = set(previous_scenarios)
    reusable = sorted(
        scenario_id
        for scenario_id in current_ids & previous_ids
        if scenario_id not in impacted
        and bool(previous_scenarios[scenario_id].get("sources"))
    )
    return {
        "full_audit_required": current_ids != previous_ids,
        "coverage_scan_required": bool(changed_sources),
        "draft_review_required": (
            manifest.get("draft_digest") != draft_inventory["draft_digest"]
        ),
        "changed_sources": sorted(changed_sources),
        "impacted_scenarios": sorted(impacted),
        "reusable_scenarios": reusable,
        "preserved_out_of_scope": sorted(set(preserved_out_of_scope)),
        "missing_sources": missing_sources,
        "added_scenarios": sorted(current_ids - previous_ids),
        "removed_scenarios": sorted(previous_ids - current_ids),
    }


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_structured_state(
    draft: Path,
    draft_inventory: dict[str, Any],
    specs: list[SourceSpec],
    ledger: dict[str, Any],
    run_scope: str,
    scope_ids: set[str],
    base_state_digest: str | None,
) -> dict[str, Any]:
    roots = source_roots(specs)
    existing = load_structured_state(draft)
    existing_manifest = existing["manifest"]
    if base_state_digest and existing_manifest.get("state_digest") != base_state_digest:
        raise ValueError("state changed after analysis; reload the canonical draft before writing")

    draft_by_id = {
        scenario["id"]: scenario for scenario in draft_inventory["scenarios"]
    }
    ledger_entries = ledger["scenarios"]
    unknown_ids = sorted(set(ledger_entries) - set(draft_by_id))
    if unknown_ids:
        raise ValueError(f"ledger contains unknown scenarios: {', '.join(unknown_ids)}")

    allowed_sources = scope_ids or set(roots)
    if not allowed_sources <= set(roots):
        unknown = sorted(allowed_sources - set(roots))
        raise ValueError(f"scope names inaccessible sources: {', '.join(unknown)}")
    if run_scope == "full" and set(ledger_entries) != set(draft_by_id):
        missing = sorted(set(draft_by_id) - set(ledger_entries))
        raise ValueError(
            "full state write requires evidence for every scenario"
            + (f": {', '.join(missing)}" if missing else "")
        )
    if run_scope == "full" and scope_ids and scope_ids != set(roots):
        raise ValueError("full state write requires every accessible source in scope")
    if run_scope == "contribution" and not scope_ids:
        raise ValueError("contribution state write requires at least one --scope")

    normalized = {
        scenario_id: normalize_ledger_scenario(
            scenario_id,
            entry,
            roots,
            allowed_sources,
        )
        for scenario_id, entry in ledger_entries.items()
    }

    previous = existing["scenarios"]
    if run_scope == "contribution":
        if not previous and set(ledger_entries) != set(draft_by_id):
            raise ValueError(
                "the first state write must cover every published scenario before scoped "
                "contributions can preserve unavailable evidence"
            )
        removed = sorted(set(previous) - set(draft_by_id))
        if removed:
            raise ValueError(
                "a contribution run cannot remove scenarios outside a full reconciliation"
            )
        changed_without_evidence = sorted(
            scenario_id
            for scenario_id, prior in previous.items()
            if scenario_id in draft_by_id
            and scenario_id not in normalized
            and prior.get("body_hash") != draft_by_id[scenario_id]["body_hash"]
        )
        if changed_without_evidence:
            raise ValueError(
                "a contribution run cannot change scenarios without scoped evidence: "
                + ", ".join(changed_without_evidence)
            )
        scenario_state = {
            scenario_id: {
                "title": prior.get("title"),
                "body_hash": prior.get("body_hash"),
                "sources": prior.get("sources", []),
            }
            for scenario_id, prior in previous.items()
            if scenario_id in draft_by_id
        }
    else:
        scenario_state = {}

    for scenario_id, current in draft_by_id.items():
        if scenario_id in normalized:
            normalized_entry = normalized[scenario_id]
            if run_scope == "contribution" and scenario_id in previous:
                preserved_sources = [
                    source
                    for source in previous[scenario_id].get("sources", [])
                    if source.get("source_id") not in allowed_sources
                ]
                normalized_entry = {
                    **normalized_entry,
                    "sources": sorted(
                        [*preserved_sources, *normalized_entry["sources"]],
                        key=lambda item: (item["source_id"], item["path"]),
                    ),
                }
            scenario_state[scenario_id] = {
                "title": current["title"],
                "body_hash": current["body_hash"],
                **normalized_entry,
            }
        elif scenario_id in scenario_state:
            scenario_state[scenario_id] = {
                **scenario_state[scenario_id],
                "title": current["title"],
                "body_hash": current["body_hash"],
            }

    previous_sources = existing["sources"]
    source_state = (
        {
            source_id: {
                key: value
                for key, value in prior.items()
                if key
                in {
                    "source_id",
                    "kind",
                    "revision",
                    "dirty",
                    "fingerprint",
                }
            }
            for source_id, prior in previous_sources.items()
        }
        if run_scope == "contribution"
        else {}
    )
    for spec in specs:
        if spec.source_id not in allowed_sources and run_scope == "contribution":
            continue
        root = roots[spec.source_id]
        git = git_metadata(root)
        source_state[spec.source_id] = {
            "source_id": spec.source_id,
            "kind": spec.kind,
            "revision": git.get("commit"),
            "dirty": git.get("dirty"),
            "fingerprint": root_fingerprint(
                root,
                draft if draft == root or draft.is_relative_to(root) else None,
            ),
        }

    legacy_dir = draft / LEGACY_STATE_DIR_NAME
    if legacy_dir.exists():
        validate_legacy_layout(draft)

    state = build_unified_state(
        draft_inventory,
        run_scope,
        source_state,
        scenario_state,
    )
    write_json(draft / STATE_FILE_NAME, state)
    if legacy_dir.exists():
        cleanup_legacy_state(draft)
    return state


def main() -> int:
    args = parse_args()
    draft = Path(args.draft_path).expanduser().resolve()
    if not draft.is_dir():
        raise SystemExit(f"draft path is not a directory: {draft}")
    try:
        specs = collect_sources(args)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    roots_by_id = source_roots(specs)
    report = inventory(draft)
    state = load_structured_state(draft)
    report["state_path"] = str(draft / STATE_FILE_NAME)
    report["state_found"] = bool(state["manifest"])
    report["state_format"] = state["format"]
    report["legacy_state_found"] = (draft / LEGACY_STATE_DIR_NAME).is_dir()
    report["state_schema_version"] = state["manifest"].get("schema_version")
    report["state_digest"] = state["manifest"].get("state_digest")
    report["accessible_sources"] = sorted(roots_by_id)
    report["run_scope"] = args.run_scope

    if args.check_state:
        report["incremental"] = structured_compare(report, state, roots_by_id)

    if args.migrate_state:
        try:
            migrated = migrate_legacy_state(draft)
        except ValueError as error:
            raise SystemExit(str(error)) from error
        report["state_found"] = True
        report["state_written"] = True
        report["state_migrated"] = True
        report["state_format"] = "unified"
        report["legacy_state_found"] = False
        report["state_schema_version"] = migrated["schema_version"]
        report["state_digest"] = migrated["state_digest"]

    if args.write_state:
        if args.run_scope == "audit":
            raise SystemExit("--write-state cannot be used with --run-scope audit")
        try:
            ledger = load_evidence_ledger(args.evidence_ledger)
            state_value = write_structured_state(
                draft,
                report,
                specs,
                ledger,
                args.run_scope,
                set(args.scope),
                args.base_state_digest,
            )
        except ValueError as error:
            raise SystemExit(str(error)) from error
        report["state_found"] = True
        report["state_written"] = True
        report["state_format"] = "unified"
        report["legacy_state_found"] = False
        report["state_schema_version"] = state_value["schema_version"]
        report["state_digest"] = state_value["state_digest"]

    output = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        Path(args.output).expanduser().write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
