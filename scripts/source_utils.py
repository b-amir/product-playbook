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
    parsed = urlsplit(locator)
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
