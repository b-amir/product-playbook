#!/usr/bin/env python3
"""Parse and acquire portable evidence-source specifications."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import SplitResult, urlsplit, urlunsplit


SOURCE_ID = re.compile(r"^[a-z][a-z0-9-]{0,62}$")
REMOTE_SCHEMES = {"file", "git", "http", "https", "ssh"}
WORKSPACE_MEMBER_SKIP = {
    ".agents",
    ".cache",
    ".claude",
    ".codex",
    ".cursor",
    ".git",
    ".github",
    ".impeccable",
    ".venv",
    ".vscode",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "graphify-out",
    "local",
    "node_modules",
    "out",
    "playbook-findings",
    "playwright-report",
    "target",
    "test-results",
    "vendor",
}
WORKSPACE_MEMBER_MARKERS = {
    "Cargo.toml",
    "Gemfile",
    "Makefile",
    "Package.swift",
    "build.gradle",
    "build.gradle.kts",
    "composer.json",
    "go.mod",
    "mix.exs",
    "package.json",
    "pom.xml",
    "pubspec.yaml",
    "pyproject.toml",
    "requirements.txt",
    "setup.cfg",
    "setup.py",
}
WORKSPACE_MEMBER_DIR_HINTS = {
    "api",
    "app",
    "apps",
    "backend",
    "docs",
    "frontend",
    "lib",
    "packages",
    "services",
    "src",
    "web",
}
KNOWN_WORKSPACE_ROOT_NAMES = {
    "admin",
    "api",
    "automation",
    "backend",
    "client",
    "contracts",
    "docs",
    "documentation",
    "frontend",
    "infra",
    "mobile",
    "sdk",
    "server",
    "unified-docs",
    "web",
    "worker",
}


@dataclass(frozen=True)
class SourceSpec:
    source_id: str
    locator: str
    kind: str = "code"
    ref: str | None = None


@dataclass(frozen=True)
class AcquiredSource:
    source_id: str
    kind: str
    root: Path
    locator_type: str
    portable_locator: str | None
    revision: str | None
    cleanup_required: bool


def parse_source_spec(raw: str, kind: str = "code") -> SourceSpec:
    if "=" not in raw:
        raise ValueError("source must use SOURCE_ID=PATH_OR_URL")
    source_id, locator = raw.split("=", 1)
    source_id = source_id.strip().lower()
    locator = locator.strip()
    if not SOURCE_ID.fullmatch(source_id):
        raise ValueError(
            "source ID must start with a lowercase letter and contain only "
            "lowercase letters, digits, and hyphens"
        )
    if not locator:
        raise ValueError("source locator must not be empty")
    return SourceSpec(source_id=source_id, locator=locator, kind=kind)


def is_remote_locator(locator: str) -> bool:
    if re.match(r"^[^/@\s]+@[^:\s]+:.+", locator):
        return True
    return urlsplit(locator).scheme.lower() in REMOTE_SCHEMES


def sanitize_remote_locator(locator: str) -> str:
    if re.match(r"^[^/@\s]+@[^:\s]+:.+", locator):
        return locator
    try:
        parsed = urlsplit(locator)
    except ValueError:
        return locator
    if not parsed.scheme:
        return locator
    hostname = parsed.hostname or ""
    if parsed.port:
        hostname = f"{hostname}:{parsed.port}"
    sanitized = SplitResult(
        scheme=parsed.scheme,
        netloc=hostname,
        path=parsed.path,
        query="",
        fragment="",
    )
    return urlunsplit(sanitized)


def git_revision(root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    revision = result.stdout.strip()
    return revision if result.returncode == 0 and revision else None


def _git_text(root: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    value = result.stdout.strip()
    return value if result.returncode == 0 and value else None


def git_repository_identity(root: Path) -> dict[str, object]:
    """Return runtime-only local and sanitized remote repository addresses."""

    git_root_raw = _git_text(root, "rev-parse", "--show-toplevel")
    if not git_root_raw:
        return {
            "local_root": str(root.resolve()),
            "git_root": None,
            "branch": None,
            "remotes": [],
        }

    git_root = Path(git_root_raw).resolve()
    branch = _git_text(git_root, "branch", "--show-current")
    remote_names = (_git_text(git_root, "remote") or "").splitlines()
    remotes: list[dict[str, str]] = []
    for name in sorted(remote_names):
        fetch_url = _git_text(git_root, "remote", "get-url", name)
        push_url = _git_text(git_root, "remote", "get-url", "--push", name)
        if not fetch_url:
            continue
        item = {
            "name": name,
            "fetch_url": sanitize_remote_locator(fetch_url),
        }
        if push_url:
            sanitized_push = sanitize_remote_locator(push_url)
            if sanitized_push != item["fetch_url"]:
                item["push_url"] = sanitized_push
        remotes.append(item)

    return {
        "local_root": str(root.resolve()),
        "git_root": str(git_root),
        "branch": branch,
        "remotes": remotes,
    }


def discover_nested_git_repositories(
    root: Path,
    *,
    max_depth: int = 4,
) -> list[dict[str, object]]:
    """Find checked-out repositories nested inside a wrapper workspace."""

    root = root.resolve()
    discovered: dict[str, dict[str, object]] = {}
    root_depth = len(root.parts)
    for current, directories, names in os.walk(root):
        current_path = Path(current)
        depth = len(current_path.parts) - root_depth
        has_git_marker = ".git" in directories or ".git" in names
        directories[:] = [
            directory
            for directory in sorted(directories)
            if directory
            not in {
                ".git",
                ".cache",
                ".venv",
                "__pycache__",
                "build",
                "coverage",
                "dist",
                "node_modules",
                "target",
                "vendor",
            }
        ]
        if depth >= max_depth:
            directories[:] = []
        if current_path == root or not has_git_marker:
            continue
        identity = git_repository_identity(current_path)
        git_root = identity.get("git_root")
        if not isinstance(git_root, str) or Path(git_root) == root:
            continue
        discovered[git_root] = {
            "path": str(Path(git_root).relative_to(root)),
            **identity,
        }
        directories[:] = []
    return sorted(discovered.values(), key=lambda item: str(item["path"]))


def _read_gitmodules_paths(root: Path) -> list[str]:
    gitmodules = root / ".gitmodules"
    if not gitmodules.is_file():
        return []
    paths: list[str] = []
    try:
        text = gitmodules.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    for match in re.finditer(r"^\s*path\s*=\s*(.+)\s*$", text, re.MULTILINE):
        value = match.group(1).strip()
        if value:
            paths.append(value)
    return paths


def _looks_like_product_member(path: Path) -> bool:
    if not path.is_dir():
        return False
    try:
        entries = list(path.iterdir())
    except OSError:
        return False
    names = {entry.name for entry in entries}
    if names & WORKSPACE_MEMBER_MARKERS:
        return True
    if names & WORKSPACE_MEMBER_DIR_HINTS:
        return True
    lowered = {name.lower() for name in names}
    if lowered & {marker.lower() for marker in WORKSPACE_MEMBER_MARKERS}:
        return True
    # Lightweight source presence without walking the whole tree.
    for entry in entries[:40]:
        if entry.is_file() and entry.suffix.lower() in {
            ".ts",
            ".tsx",
            ".js",
            ".jsx",
            ".py",
            ".go",
            ".rs",
            ".java",
            ".cs",
            ".md",
        }:
            return True
        if entry.is_dir() and entry.name.lower() in WORKSPACE_MEMBER_DIR_HINTS:
            return True
    return False


def infer_workspace_member_roles(relative_path: str) -> list[str]:
    role_tokens = {
        "docs": {"docs", "documentation", "handbook", "unified-docs"},
        "frontend": {"frontend", "web", "ui"},
        "api": {"api", "backend", "server"},
        "rag": {"rag", "retrieval", "search", "vector"},
        "worker": {"worker", "jobs", "consumer"},
        "integration": {"integration", "connector", "adapter"},
        "sdk": {"sdk", "client"},
        "library": {"shared", "common", "helper", "helpers", "library", "package"},
        "tooling": {"automation", "scripts", "tools", "tooling"},
    }
    path_tokens = {
        token
        for part in Path(relative_path).parts
        for token in re.split(r"[-_. ]+", part.lower())
        if token
    }
    roles = [role for role, tokens in role_tokens.items() if path_tokens & tokens]
    return roles or ["unknown"]


def sanitize_source_id(raw: str, *, fallback: str) -> str:
    cleaned = re.sub(r"[^a-z0-9-]+", "-", raw.lower()).strip("-")
    cleaned = re.sub(r"-{2,}", "-", cleaned)
    if cleaned and SOURCE_ID.fullmatch(cleaned):
        return cleaned
    if SOURCE_ID.fullmatch(fallback):
        return fallback
    return "member"


def allocate_source_id(preferred: str, parent_id: str, used: set[str]) -> str:
    base = sanitize_source_id(preferred, fallback=f"{parent_id}-member")
    if base not in used:
        return base
    prefixed = sanitize_source_id(f"{parent_id}-{base}", fallback=f"{parent_id}-member")
    if prefixed not in used:
        return prefixed
    index = 2
    while True:
        candidate = sanitize_source_id(
            f"{prefixed}-{index}", fallback=f"{parent_id}-member-{index}"
        )
        if candidate not in used:
            return candidate
        index += 1


def _is_expandable_workspace_sibling(path: Path) -> bool:
    """First-level siblings worth scanning as separate roots.

    Avoid treating normal monorepo package folders (`apps/`, `services/`) as
    workspace members unless they look like standalone product checkouts.
    """
    if not path.is_dir():
        return False
    if any((path / marker).is_file() for marker in WORKSPACE_MEMBER_MARKERS):
        return True
    if path.name.lower() in KNOWN_WORKSPACE_ROOT_NAMES:
        return _looks_like_product_member(path)
    return False


def discover_workspace_members(root: Path) -> list[dict[str, object]]:
    """Expand a workspace folder into nested repos, submodules, and product subfolders.

    A single source path is not assumed to be one git repository. When nested
    checkouts or product-looking siblings exist, each becomes its own scan root.
    """

    root = root.resolve()
    members: dict[str, dict[str, object]] = {}

    for nested in discover_nested_git_repositories(root):
        rel = str(nested.get("path") or "")
        git_root = nested.get("git_root")
        if not rel or not isinstance(git_root, str):
            continue
        members[rel] = {
            "path": rel,
            "root": git_root,
            "kind": "nested-git",
            "assumed_roles": infer_workspace_member_roles(rel),
            "repository_identity": {
                key: value
                for key, value in nested.items()
                if key not in {"path", "assumed_roles", "playbook_candidates"}
            },
        }

    for rel in _read_gitmodules_paths(root):
        member_root = (root / rel).resolve()
        if not member_root.is_dir() or rel in members:
            continue
        identity = git_repository_identity(member_root)
        members[rel] = {
            "path": rel,
            "root": str(member_root),
            "kind": "submodule",
            "assumed_roles": infer_workspace_member_roles(rel),
            "repository_identity": identity,
        }

    try:
        children = sorted(root.iterdir(), key=lambda item: item.name.lower())
    except OSError:
        children = []
    product_siblings: list[dict[str, object]] = []
    for child in children:
        if not child.is_dir() or child.name in WORKSPACE_MEMBER_SKIP:
            continue
        if child.name.startswith("."):
            continue
        rel = child.name
        if rel in members:
            continue
        if not _is_expandable_workspace_sibling(child):
            continue
        product_siblings.append(
            {
                "path": rel,
                "root": str(child.resolve()),
                "kind": "product-subfolder",
                "assumed_roles": infer_workspace_member_roles(rel),
                "repository_identity": git_repository_identity(child),
            }
        )

    # A normal single repo with src/app is NOT a workspace. Expand only when
    # nested checkouts/submodules exist, or when multiple standalone product
    # siblings sit side by side (frontend + backend style wrappers).
    if members:
        for sibling in product_siblings:
            members[str(sibling["path"])] = sibling
        return sorted(members.values(), key=lambda item: str(item["path"]))
    if len(product_siblings) >= 2:
        return sorted(product_siblings, key=lambda item: str(item["path"]))
    return []


def expand_acquired_sources(
    sources: list[AcquiredSource],
) -> tuple[list[AcquiredSource], list[dict[str, object]]]:
    """Expand workspace wrappers into per-member acquired sources.

    Returns the expanded source list plus expansion metadata for Intake/notes.
    """

    expanded: list[AcquiredSource] = []
    expansions: list[dict[str, object]] = []
    used_ids = {source.source_id for source in sources}

    for source in sources:
        if source.kind != "code":
            expanded.append(source)
            continue
        members = discover_workspace_members(source.root)
        if not members:
            expanded.append(source)
            continue

        child_ids: list[str] = []
        for member in members:
            rel = str(member["path"])
            roles = [str(role) for role in (member.get("assumed_roles") or [])]
            preferred = Path(rel).name
            child_id = allocate_source_id(preferred, source.source_id, used_ids)
            used_ids.add(child_id)
            child_ids.append(child_id)
            member_root = Path(str(member["root"]))
            # Every workspace member gets a full repository scan. Docs-shaped
            # members still surface as documentation via discovery signals.
            expanded.append(
                AcquiredSource(
                    source_id=child_id,
                    kind="code",
                    root=member_root,
                    locator_type=source.locator_type,
                    portable_locator=source.portable_locator,
                    revision=git_revision(member_root),
                    cleanup_required=False,
                )
            )
        expansions.append(
            {
                "parent_source_id": source.source_id,
                "parent_root": str(source.root),
                "member_source_ids": child_ids,
                "members": [
                    {
                        "source_id": child_id,
                        "path": member["path"],
                        "root": member["root"],
                        "kind": member["kind"],
                        "assumed_roles": member.get("assumed_roles") or [],
                    }
                    for child_id, member in zip(child_ids, members)
                ],
            }
        )
    return expanded, expansions


def create_workspace() -> Path:
    return Path(tempfile.mkdtemp(prefix="product-playbook-sources-"))


def acquire_source(spec: SourceSpec, workspace: Path | None = None) -> AcquiredSource:
    if not is_remote_locator(spec.locator):
        root = Path(spec.locator).expanduser().resolve()
        if not root.is_dir():
            raise ValueError(f"source is not a directory: {spec.source_id}")
        return AcquiredSource(
            source_id=spec.source_id,
            kind=spec.kind,
            root=root,
            locator_type="local",
            portable_locator=None,
            revision=git_revision(root),
            cleanup_required=False,
        )

    checkout_root = workspace or create_workspace()
    checkout_root.mkdir(parents=True, exist_ok=True)
    destination = checkout_root / spec.source_id
    if destination.exists():
        raise ValueError(f"source checkout destination already exists: {spec.source_id}")

    commands = (
        [
            ["git", "init", str(destination)],
            ["git", "-C", str(destination), "remote", "add", "origin", spec.locator],
            [
                "git",
                "-C",
                str(destination),
                "fetch",
                "--depth",
                "1",
                "origin",
                spec.ref,
            ],
            [
                "git",
                "-C",
                str(destination),
                "checkout",
                "--detach",
                "FETCH_HEAD",
            ],
        ]
        if spec.ref
        else [
            [
                "git",
                "clone",
                "--depth",
                "1",
                "--single-branch",
                spec.locator,
                str(destination),
            ]
        ]
    )
    for command in commands:
        try:
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=300,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            if destination.exists():
                shutil.rmtree(destination)
            raise ValueError(f"could not acquire source {spec.source_id}: {error}") from error
        if result.returncode != 0:
            detail = result.stderr.strip().splitlines()
            message = detail[-1] if detail else "git acquisition failed"
            message = message.replace(spec.locator, sanitize_remote_locator(spec.locator))
            if destination.exists():
                shutil.rmtree(destination)
            raise ValueError(f"could not acquire source {spec.source_id}: {message}")

    return AcquiredSource(
        source_id=spec.source_id,
        kind=spec.kind,
        root=destination.resolve(),
        locator_type="remote",
        portable_locator=sanitize_remote_locator(spec.locator),
        revision=git_revision(destination),
        cleanup_required=True,
    )


def legacy_specs(code_repos: list[str], docs_paths: list[str]) -> list[SourceSpec]:
    specs = [
        SourceSpec(source_id=f"code-{index}", locator=locator, kind="code")
        for index, locator in enumerate(code_repos, start=1)
    ]
    specs.extend(
        SourceSpec(source_id=f"docs-{index}", locator=locator, kind="docs")
        for index, locator in enumerate(docs_paths, start=1)
    )
    return specs


def ensure_unique_sources(specs: list[SourceSpec]) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for spec in specs:
        if spec.source_id in seen:
            duplicates.add(spec.source_id)
        seen.add(spec.source_id)
    if duplicates:
        raise ValueError(f"duplicate source IDs: {', '.join(sorted(duplicates))}")
