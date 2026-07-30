#!/usr/bin/env python3
"""Discover product surfaces, tests, interfaces, docs, and existing playbook drafts."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from source_utils import (
    SourceSpec,
    acquire_source,
    create_workspace,
    discover_nested_git_repositories,
    ensure_unique_sources,
    expand_acquired_sources,
    git_repository_identity,
    is_remote_locator,
    legacy_specs,
    parse_source_spec,
    sanitize_remote_locator,
)


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
    "node_modules",
    "out",
    "playwright-report",
    "target",
    "test-results",
    "vendor",
}
SOURCE_SUFFIXES = {
    ".bats",
    ".cjs",
    ".cs",
    ".dart",
    ".ex",
    ".exs",
    ".go",
    ".java",
    ".js",
    ".jsx",
    ".kt",
    ".lua",
    ".mjs",
    ".php",
    ".py",
    ".rb",
    ".rs",
    ".scala",
    ".sh",
    ".swift",
    ".ts",
    ".tsx",
    ".zig",
}
VIEWPORT_FORK_SUFFIXES = SOURCE_SUFFIXES | {
    ".css",
    ".less",
    ".sass",
    ".scss",
    ".svelte",
    ".vue",
}
AUTH_ROLE_MARKERS = (
    ("role.admin", "named role constant"),
    ("role.member", "named role constant"),
    ("role.viewer", "named role constant"),
    ("roles.admin", "named role constant"),
    ("user_role", "user_role field"),
    ("userrole", "user role model"),
    ("roletier", "role tier type"),
    ("role_tier", "role tier field"),
)
# Chat / LLM message roles — never product personas.
AUTH_CHAT_ROLE_LABELS = {
    "user",
    "assistant",
    "system",
    "tool",
    "function",
    "model",
    "developer",
}
# Permission actions, UI nouns, ORM fields, agent-tool personas — not product roles.
AUTH_ROLE_LABEL_STOPWORDS = {
    "role",
    "roles",
    "user",
    "users",
    "type",
    "name",
    "id",
    "true",
    "false",
    "null",
    "none",
    "string",
    "number",
    "boolean",
    "page",
    "acl",
    "guard",
    "auth",
    "permission",
    "permissions",
    "module",
    "action",
    "suspend",
    "view",
    "invite",
    "share",
    "approve",
    "archive",
    "upload",
    "export",
    "edit",
    "create",
    "delete",
    "update",
    "read",
    "write",
    "manage",
    "access",
    "status",
    "content",
    "createdat",
    "updatedat",
    "optimistic",
    "second",
    "first",
    "default",
    "internal",
    "external",
    "active",
    "inactive",
    "fixer",
    "scout",
    "reviewer",
    "closer",
    "writer",
    "qa",
    "admin table row action",
}
# Weak-pattern hits must be in this vocabulary (slugs). Strong definition blocks may
# introduce additional labels after stopword filtering.
AUTH_KNOWN_ROLE_SLUGS = {
    "admin",
    "administrator",
    "member",
    "viewer",
    "owner",
    "editor",
    "guest",
    "manager",
    "operator",
    "superuser",
    "super admin",
    "super_admin",
    "billing admin",
    "billing_admin",
    "read only",
    "read_only",
    "readonly",
    "contributor",
    "maintainer",
    "standard user",
    "standard_user",
    "client",
    "prospect",
    "external partner",
    "external_partner",
    "client standard",
    "client_standard",
    "k2 internal",
    "k2_internal",
}
AUTH_ROLE_NOISE_PATH_PARTS = {
    "automation",
    "node_modules",
    ".agents",
    "agents/fixtures",
}
# Strong: role / tier definition blocks. Captures enum members and union literals.
# Product-agnostic: quoted values inside these blocks are kept after stopword
# filtering, even when they are not in AUTH_KNOWN_ROLE_SLUGS.
AUTH_ROLE_DEFINITION_PATTERNS = (
    re.compile(
        r"\benum\s+Roles?\b[^{]*\{([^}]{0,2000})\}",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"\bclass\s+Roles?\b[^\n]*\bEnum\b[^{]*\{([^}]{0,2000})\}",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"\bclass\s+Roles?\b[^\n]*\bEnum\b[^:]*:((?:\n[ \t]+[^\n]+){1,80})",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:export\s+)?type\s+\w*(?:Role|Tier|Persona|Actor)\w*\s*=\s*([^;]{0,1200})",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"\b(?:RoleTier|UserRole|AccountRole|Roles?|Persona|Actor)\s*=\s*"
        r"z\.enum\(\[([^\]]{0,1200})\]",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r'["\'](?:RoleTier|UserRole|AccountRole|Roles?|Persona|Actor)["\']\s*:\s*'
        r'\{[^{}]{0,200}"enum"\s*:\s*\[([^\]]{0,1200})\]',
        re.IGNORECASE | re.DOTALL,
    ),
)
# Factory / seed display names: role("Administrator", "administrator")
AUTH_ROLE_FACTORY_PATTERN = re.compile(
    r"\brole\s*\(\s*['\"]([^'\"]{2,40})['\"]\s*,\s*['\"]([A-Za-z_][A-Za-z0-9_-]*)['\"]",
    re.IGNORECASE,
)
# Weak: only kept when the captured token is in AUTH_KNOWN_ROLE_SLUGS.
# This list is a precision aid for common SaaS names, not a product allowlist.
# Custom product roles must come from definition blocks / factories above.
AUTH_ROLE_WEAK_PATTERNS = (
    re.compile(r"\bRole(?:s)?\.([A-Za-z_][A-Za-z0-9_]*)"),
    re.compile(
        r"\b(?:roleTier|role_tier|userRole|user_role|accountType|account_type)"
        r"\s*[:=]\s*['\"]([A-Za-z_][A-Za-z0-9_-]*)['\"]",
        re.IGNORECASE,
    ),
    re.compile(
        r"['\"](admin|administrator|member|viewer|owner|editor|guest|manager|"
        r"operator|superuser|super_admin|billing|billing_admin|read_only|readonly|"
        r"contributor|maintainer|standard_user|client|prospect|external_partner)['\"]",
        re.IGNORECASE,
    ),
)
AUTH_GATE_MARKERS = (
    ("require_auth", "auth required"),
    ("requiresauth", "auth required"),
    ("require_role", "role required"),
    ("requirerole", "role required"),
    ("has_permission", "permission check"),
    ("haspermission", "permission check"),
    ("check_permission", "permission check"),
    ("permissiongate", "permission gate"),
    ("canactivate", "route guard"),
    ("authorize(", "authorize call"),
)
VIEWPORT_FORK_MARKERS = (
    ("@media", "CSS media query"),
    ("matchmedia", "matchMedia usage"),
    ("usemediaquery", "useMediaQuery hook"),
    ("usebreakpoint", "useBreakpoint hook"),
    ("setviewportsize", "Playwright viewport size"),
    ("cy.viewport", "Cypress viewport"),
    ('addeventlistener("resize"', "resize listener"),
    ("addeventlistener('resize'", "resize handler"),
    ("onwindowresize", "resize handler"),
    ("ismobile(", "isMobile helper"),
    ("isdesktop(", "isDesktop helper"),
    ("const ismobile", "isMobile branch"),
    ("let ismobile", "isMobile branch"),
    ("mobilevariant", "mobile/desktop variant split"),
    ("desktopvariant", "mobile/desktop variant split"),
    ("mobileonly", "mobile-only branch"),
    ("desktoponly", "desktop-only branch"),
    ("md:hidden", "responsive utility class"),
    ("hidden md:", "responsive utility class"),
    ("sm:hidden", "responsive utility class"),
    ("lg:block", "responsive utility class"),
)
# When a viewport fork also gates by role/permission, rank it higher — that is
# where narrow/wide bugs like "icon visible on mobile only" show up.
VIEWPORT_AUTH_CROSSOVER_MARKERS = (
    "usepermission",
    "permissiongate",
    "haspermission",
    "require_role",
    "requirerole",
    "canmanage",
    "roletier",
    "role_tier",
    "oninviteuser",
    "users:invite",
    "authorize(",
)
DOC_SUFFIXES = {".adoc", ".md", ".mdx", ".rst", ".txt"}
CONTRACT_SUFFIXES = {".graphql", ".gql", ".proto", ".raml"}
STRUCTURED_CONTRACT_SUFFIXES = {".json", ".yaml", ".yml"}
SURFACE_CHOICES = (
    "auto",
    "frontend",
    "api",
    "fullstack",
    "cli",
    "service",
    "worker",
    "mobile",
    "rag",
    "library",
    "sdk",
    "integration",
    "extension",
    "data",
    "contracts",
    "docs",
    "tooling",
)
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
    "Makefile",
    "Justfile",
    "justfile",
}
TEST_NAME = re.compile(
    r"(^test_|_test\.|\.test\.|\.spec\.|\.cy\.|tests?\.|_spec\.)",
    re.IGNORECASE,
)
PAGE_OBJECT_NAME = re.compile(r"(^|[-_.])(page|page[-_]?object)([-_.]|$)", re.IGNORECASE)
INTERFACE_NAME = re.compile(
    r"(route|router|routing|controller|endpoint|handler|urls|command|cli|worker|job|consumer|"
    r"retriev|embedding|vector|guardrail|connector|adapter|webhook)",
    re.IGNORECASE,
)
DOCUMENTATION_NAME = re.compile(
    r"(playbook|manual|scenario|test[-_ ]?plan|testing[-_ ]?strategy|qa|uat|runbook|"
    r"test[-_ ]?report|results?|acceptance|postman|insomnia)",
    re.IGNORECASE,
)
DOCUMENTATION_DIRS = {
    "api scenarios",
    "docs",
    "documentation",
    "manual",
    "playbook",
    "qa",
    "runbooks",
    "scenarios",
}
URL_PATTERN = re.compile(r"\b(?:https?|wss?)://[^\s<>'\"`]+", re.IGNORECASE)
ADDRESS_VARIABLE = re.compile(
    r"\b(?:VITE_|NEXT_PUBLIC_|PUBLIC_)?(?:API|APP|BACKEND|FRONTEND|SERVICE|OPENAPI|"
    r"SWAGGER|RAG|VECTOR|DOCS|GRAPHQL)[A-Z0-9_]*(?:URL|URI|HOST|ENDPOINT)\b"
)
SECRET_FILE_NAME = re.compile(
    r"(^|[._-])(env|secret|credential|token|password|private[-_]?key)([._-]|$)",
    re.IGNORECASE,
)
LOCKFILE_NAMES = {
    "bun.lock",
    "bun.lockb",
    "cargo.lock",
    "composer.lock",
    "gemfile.lock",
    "package-lock.json",
    "pnpm-lock.yaml",
    "poetry.lock",
    "uv.lock",
    "yarn.lock",
}
SCENARIO_HEADING = re.compile(
    r"^## [A-Z][A-Z0-9]{1,5}-\d{2,3}:", re.MULTILINE
)
CONVENTIONAL_DRAFT_DIRS = (
    "docs/playbook",
    "docs/manual-testing-playbook",
    "docs/manual-test-playbook",
    "docs/testing-playbook",
    "manual-testing-playbook",
    "playbook",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Produce a product-neutral discovery report for browser, API, service, or CLI projects."
    )
    parser.add_argument(
        "--code-repo",
        action="append",
        default=[],
        help="Local code repository path. Repeat for multiple repositories.",
    )
    parser.add_argument(
        "--docs-path",
        action="append",
        default=[],
        help="Local documentation path. Repeat for multiple roots.",
    )
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        metavar="SOURCE_ID=PATH_OR_URL",
        help="Portable code source. Repeat for multiple sources.",
    )
    parser.add_argument(
        "--docs-source",
        action="append",
        default=[],
        metavar="SOURCE_ID=PATH_OR_URL",
        help="Portable documentation source. Repeat for multiple sources.",
    )
    parser.add_argument(
        "--source-ref",
        action="append",
        default=[],
        metavar="SOURCE_ID=REF",
        help="Optional branch, tag, or commit for a remote source.",
    )
    parser.add_argument(
        "--workspace-dir",
        help="Directory for remote read-only checkouts. A temporary directory is created by default.",
    )
    parser.add_argument(
        "--test-framework",
        default="auto",
        help="Framework override. Defaults to auto-detection.",
    )
    parser.add_argument(
        "--product-surface",
        choices=SURFACE_CHOICES,
        default="auto",
        help="Product-surface override. Defaults to auto-detection.",
    )
    parser.add_argument("--draft-path", help="Explicit existing playbook file or directory")
    parser.add_argument("--output-dir", help="Requested playbook destination")
    parser.add_argument("--output", help="Write JSON to this file instead of stdout")
    parser.add_argument(
        "--max-items",
        type=int,
        default=500,
        help="Maximum paths returned per category and repository",
    )
    return parser.parse_args()


def walk_files(root: Path, max_depth: int | None = None) -> list[Path]:
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
                relative_path = Path(raw.decode("utf-8", errors="replace"))
                if any(part in SKIP_DIRS for part in relative_path.parts):
                    continue
                if max_depth is not None and len(relative_path.parts) - 1 > max_depth:
                    continue
                path = root / relative_path
                if path.is_file():
                    files.append(path)
            return sorted(files)

    files: list[Path] = []
    root_depth = len(root.parts)
    for current, dirs, names in os.walk(root):
        current_path = Path(current)
        depth = len(current_path.parts) - root_depth
        if max_depth is not None and depth >= max_depth:
            dirs[:] = []
        else:
            dirs[:] = sorted(
                directory
                for directory in dirs
                if directory not in SKIP_DIRS and not directory.startswith(".cache")
            )
        files.extend(current_path / name for name in sorted(names))
    return files


def relative(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def read_text(path: Path, limit: int = 250_000) -> str:
    try:
        if path.stat().st_size > limit:
            return ""
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def select_manifests(files: list[Path], root: Path) -> tuple[str, list[str]]:
    selected = [
        path
        for path in files
        if path.name in MANIFEST_NAMES or path.suffix.lower() == ".csproj"
    ]
    content = "\n".join(read_text(path) for path in selected)
    return content.lower(), [relative(path, root) for path in selected]


def detect_languages(files: list[Path]) -> list[str]:
    mapping = {
        ".bats": "shell",
        ".cs": "csharp",
        ".dart": "dart",
        ".ex": "elixir",
        ".exs": "elixir",
        ".go": "go",
        ".java": "java",
        ".js": "javascript",
        ".jsx": "javascript",
        ".kt": "kotlin",
        ".lua": "lua",
        ".php": "php",
        ".py": "python",
        ".rb": "ruby",
        ".rs": "rust",
        ".scala": "scala",
        ".sh": "shell",
        ".swift": "swift",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".zig": "zig",
    }
    return sorted({mapping[path.suffix.lower()] for path in files if path.suffix.lower() in mapping})


def add_signal(signals: dict[str, list[str]], name: str, reason: str) -> None:
    if reason not in signals[name]:
        signals[name].append(reason)


def detect_test_frameworks(
    files: list[Path], project_text: str, root: Path
) -> list[dict[str, Any]]:
    paths = [relative(path, root).lower() for path in files]
    names = {Path(path).name.lower() for path in paths}
    test_text = "\n".join(
        read_text(path, 100_000).lower()
        for path in files
        if TEST_NAME.search(path.name) and path.suffix.lower() in SOURCE_SUFFIXES
    )
    signals: dict[str, list[str]] = {
        "playwright": [],
        "cypress": [],
        "selenium": [],
        "pytest": [],
        "unittest": [],
        "jest": [],
        "vitest": [],
        "junit": [],
        "go-test": [],
        "rspec": [],
        "xunit": [],
        "cargo-test": [],
        "appium": [],
        "detox": [],
        "xctest": [],
        "espresso": [],
        "flutter-test": [],
        "bats": [],
    }

    if any(name.startswith("playwright.config.") for name in names):
        add_signal(signals, "playwright", "playwright.config file")
    if "@playwright/test" in project_text or re.search(r"\bplaywright\b", project_text):
        add_signal(signals, "playwright", "Playwright dependency")

    if any(name.startswith("cypress.config.") for name in names):
        add_signal(signals, "cypress", "cypress.config file")
    if re.search(r"\bcypress\b", project_text):
        add_signal(signals, "cypress", "Cypress dependency")
    if any(path.startswith("cypress/") or "/cypress/" in path for path in paths):
        add_signal(signals, "cypress", "cypress directory")

    if any(
        token in project_text
        for token in ("selenium-webdriver", "org.seleniumhq.selenium", "selenium")
    ):
        add_signal(signals, "selenium", "Selenium dependency")
    if "webdriver" in test_text:
        add_signal(signals, "selenium", "WebDriver test usage")

    if "pytest" in project_text or "pytest" in test_text or "conftest.py" in names:
        add_signal(signals, "pytest", "pytest configuration or test usage")
    if "unittest" in test_text:
        add_signal(signals, "unittest", "Python unittest usage")
    if re.search(r"\bjest\b", project_text) or any(name.startswith("jest.config.") for name in names):
        add_signal(signals, "jest", "Jest dependency or configuration")
    if re.search(r"\bvitest\b", project_text):
        add_signal(signals, "vitest", "Vitest dependency")
    if "junit" in project_text or "org.junit" in test_text:
        add_signal(signals, "junit", "JUnit dependency or test usage")
    if any(path.endswith("_test.go") for path in paths):
        add_signal(signals, "go-test", "Go test files")
    if "rspec" in project_text or any(path.endswith("_spec.rb") for path in paths):
        add_signal(signals, "rspec", "RSpec dependency or test files")
    if any(token in project_text for token in ("xunit", "nunit", "mstest")):
        add_signal(signals, "xunit", ".NET test dependency")
    if any(path.endswith(".rs") and "/tests/" in f"/{path}" for path in paths):
        add_signal(signals, "cargo-test", "Rust integration tests")
    if "appium" in project_text or "appium" in test_text:
        add_signal(signals, "appium", "Appium dependency or test usage")
    if "detox" in project_text or "device.launchapp" in test_text:
        add_signal(signals, "detox", "Detox dependency or test usage")
    if "xctest" in project_text or "xctest" in test_text:
        add_signal(signals, "xctest", "XCTest dependency or test usage")
    if "espresso" in project_text or "androidx.test.espresso" in test_text:
        add_signal(signals, "espresso", "Espresso dependency or test usage")
    if "flutter_test" in project_text or any(path.endswith("_test.dart") for path in paths):
        add_signal(signals, "flutter-test", "Flutter test dependency or files")
    if any(path.endswith(".bats") for path in paths) or "bats-core" in project_text:
        add_signal(signals, "bats", "Bats dependency or test files")

    return [
        {"name": name, "signals": reasons}
        for name, reasons in signals.items()
        if reasons
    ]


def contract_kind(path: Path) -> str | None:
    rel_lower = path.as_posix().lower()
    name = path.name.lower()
    suffix = path.suffix.lower()
    if name == ".gitkeep":
        return None
    if suffix in DOC_SUFFIXES and any(
        token in rel_lower for token in ("openapi", "swagger", "asyncapi", "graphql", "protobuf")
    ):
        return "contract-documentation"
    if suffix in SOURCE_SUFFIXES and any(
        token in rel_lower for token in ("openapi", "swagger", "asyncapi")
    ):
        if any(token in rel_lower for token in ("api-schema", "api_schema", "generated/api")):
            return "generated-api-schema"
        return "contract-tooling"
    if "asyncapi" in rel_lower:
        return "asyncapi" if name.startswith("asyncapi.") else "contract-fixture"
    if "openapi" in rel_lower:
        return "openapi" if name.startswith("openapi.") else "contract-fixture"
    if "swagger" in rel_lower:
        return "swagger" if name.startswith("swagger.") else "contract-fixture"
    if suffix in {".graphql", ".gql"}:
        return "graphql"
    if suffix == ".proto":
        return "protobuf"
    if suffix == ".raml":
        return "raml"
    if suffix in SOURCE_SUFFIXES and any(
        token in rel_lower for token in ("api-schema", "api_schema", "generated/api")
    ):
        return "generated-api-schema"
    if name in {"schema.json", "schema.yaml", "schema.yml"} and any(
        token in rel_lower for token in ("api", "graphql", "contract")
    ):
        return "api-schema"
    return None


def inspect_structured_contract(path: Path) -> dict[str, Any]:
    if path.suffix.lower() != ".json":
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict) or not ({"openapi", "swagger"} & set(data)):
        return {}
    paths = data.get("paths")
    operations = 0
    tags: set[str] = set()
    if isinstance(paths, dict):
        for path_item in paths.values():
            if not isinstance(path_item, dict):
                continue
            for method, operation in path_item.items():
                if method.lower() not in {
                    "get",
                    "post",
                    "put",
                    "patch",
                    "delete",
                    "options",
                    "head",
                    "trace",
                }:
                    continue
                operations += 1
                if isinstance(operation, dict):
                    tags.update(
                        str(tag)
                        for tag in operation.get("tags", [])
                        if isinstance(tag, str)
                    )
    servers = []
    for server in data.get("servers", []):
        if not isinstance(server, dict) or not isinstance(server.get("url"), str):
            continue
        servers.append(sanitize_remote_locator(server["url"]))
    info = data.get("info") if isinstance(data.get("info"), dict) else {}
    security_schemes = (
        data.get("components", {}).get("securitySchemes", {})
        if isinstance(data.get("components"), dict)
        else {}
    )
    return {
        "title": info.get("title"),
        "version": info.get("version"),
        "path_count": len(paths) if isinstance(paths, dict) else 0,
        "operation_count": operations,
        "tags": sorted(tags),
        "server_addresses": sorted(set(servers)),
        "security_schemes": (
            sorted(security_schemes) if isinstance(security_schemes, dict) else []
        ),
    }


def detect_contract_evidence(
    files: list[Path],
    root: Path,
    max_items: int,
) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for path in files:
        kind = contract_kind(Path(relative(path, root)))
        if not kind:
            continue
        rel = relative(path, root)
        lower_parts = {part.lower() for part in Path(rel).parts}
        if path.suffix.lower() in SOURCE_SUFFIXES:
            role = "generated-client-or-schema"
        elif lower_parts & {
            "cache",
            "cached",
            "fixtures",
            "generated",
            "test",
            "tests",
        } or any(token in rel.lower() for token in ("api-schema", "api_schema")):
            role = "cached-or-generated"
        else:
            role = "contract-snapshot"
        item: dict[str, Any] = {
            "path": rel,
            "kind": kind,
            "role": role,
            "is_contract_artifact": kind
            in {
                "api-schema",
                "asyncapi",
                "generated-api-schema",
                "graphql",
                "openapi",
                "protobuf",
                "raml",
                "swagger",
            },
        }
        summary = inspect_structured_contract(path)
        if summary:
            item["summary"] = summary
        evidence.append(item)
    return sorted(evidence, key=lambda item: item["path"])[:max_items]


def detect_contracts(files: list[Path], root: Path) -> list[str]:
    return [
        item["path"]
        for item in detect_contract_evidence(files, root, max_items=len(files) or 1)
        if item["is_contract_artifact"]
    ]


def discover_documentation_candidates(
    files: list[Path],
    root: Path,
    max_items: int,
) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    for path in files:
        if path.suffix.lower() not in DOC_SUFFIXES:
            continue
        rel = relative(path, root)
        if set(Path(rel).parts) & {".agents", ".claude", ".codex"}:
            continue
        parts = {part.lower().replace("_", " ").replace("-", " ") for part in Path(rel).parts}
        reason = None
        if path.name.lower() in {"readme.md", "readme.mdx", "readme.rst"}:
            reason = "repository or component overview"
        elif parts & DOCUMENTATION_DIRS:
            reason = "documentation directory"
        elif DOCUMENTATION_NAME.search(rel):
            reason = "manual testing, scenario, or prior-work name"
        if reason:
            candidates.append({"path": rel, "reason": reason})
    return sorted(candidates, key=lambda item: item["path"])[:max_items]


def discover_prior_work(
    files: list[Path],
    root: Path,
    max_items: int,
) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    for path in files:
        rel = relative(path, root)
        if set(Path(rel).parts) & {".agents", ".claude", ".codex"}:
            continue
        rel_lower = rel.lower()
        kind = None
        if path.name == ".product-playbook-state.json":
            kind = "product-playbook-state"
        elif DOCUMENTATION_NAME.search(rel) and path.suffix.lower() in {
            *DOC_SUFFIXES,
            ".docx",
            ".html",
            ".json",
        }:
            kind = "manual-testing-or-report"
        elif path.name.lower() in {
            "coverage.xml",
            "junit.xml",
            "test-results.xml",
        }:
            kind = "test-artifact"
        elif "postman" in rel_lower and path.suffix.lower() == ".json":
            kind = "api-client-collection"
        if kind:
            candidates.append({"path": rel, "kind": kind})
    return sorted(candidates, key=lambda item: item["path"])[:max_items]


def discover_scope_warnings(
    files: list[Path],
    root: Path,
    max_items: int,
) -> list[dict[str, str]]:
    warnings: list[dict[str, str]] = []
    patterns = (
        (
            "declared-mock-or-fixture",
            (
                "mini-mock",
                "not the real",
                "mock repository",
                "fixture repository",
                "demo repository",
            ),
        ),
        (
            "declared-source-unavailable",
            (
                "source is not available",
                "source code is not available",
                "use the remote",
            ),
        ),
        (
            "declared-generated-copy",
            (
                "this repository is generated",
                "this checkout is generated",
                "generated copy",
                "generated fixture",
            ),
        ),
    )
    for path in files:
        if path.name not in {"README.md", "AGENTS.md", "CLAUDE.md"}:
            continue
        content = read_text(path, 200_000).lower()
        for kind, phrases in patterns:
            if any(phrase in content for phrase in phrases):
                warnings.append(
                    {
                        "path": relative(path, root),
                        "kind": kind,
                        "message": (
                            "Repository text limits how this source may be treated. "
                            "Read it before accepting product-scope assumptions."
                        ),
                    }
                )
                break
    return sorted(warnings, key=lambda item: item["path"])[:max_items]


def safe_address_text(path: Path) -> str:
    if (
        SECRET_FILE_NAME.search(path.name)
        or path.name.lower() in LOCKFILE_NAMES
        or path.suffix.lower() in {".lock", ".pem", ".key"}
    ):
        return ""
    return read_text(path, 200_000)


def discover_addresses(
    files: list[Path],
    root: Path,
    contract_evidence: list[dict[str, Any]],
    max_items: int,
) -> list[dict[str, str]]:
    addresses: dict[tuple[str, str, str], dict[str, str]] = {}
    for item in contract_evidence:
        summary = item.get("summary")
        if not isinstance(summary, dict):
            continue
        for value in summary.get("server_addresses", []):
            key = ("openapi-server", str(value), item["path"])
            addresses[key] = {
                "kind": "openapi-server",
                "role": "contract-server",
                "value": str(value),
                "path": item["path"],
            }

    eligible_suffixes = {*DOC_SUFFIXES, *SOURCE_SUFFIXES, ".json", ".yaml", ".yml", ".toml"}
    for path in files:
        if path.suffix.lower() not in eligible_suffixes:
            continue
        content = safe_address_text(path)
        if not content:
            continue
        rel = relative(path, root)
        for raw in URL_PATTERN.findall(content):
            if any(token in raw for token in ("${", "{{", "}}", "<", ">")):
                continue
            value = sanitize_remote_locator(raw.rstrip(".,);]}"))
            try:
                parsed = urlsplit(value)
            except ValueError:
                continue
            if not parsed.hostname:
                continue
            key = ("runtime-url", value, rel)
            rel_parts = {part.lower() for part in Path(rel).parts}
            if rel_parts & {"test", "tests", "fixtures"} or TEST_NAME.search(path.name):
                role = "test-fixture"
            elif any(
                token in value.lower()
                for token in ("localhost", "127.0.0.1", "0.0.0.0")
            ):
                role = "local-runtime"
            elif any(
                parsed.hostname.endswith(suffix)
                for suffix in (".example", ".example.com", ".example.test")
            ) or parsed.hostname in {"example.com", "example.test", "www.example.com"}:
                role = "documentation-example"
            elif (
                "api" in parsed.hostname.split(".")[0]
                or any(
                    token in parsed.path.lower()
                    for token in ("/api", "/openapi", "/swagger", "/redoc")
                )
                or any(
                    token in rel.lower()
                    for token in ("backend", "service", "api scenario")
                )
            ):
                role = "api-or-service"
            else:
                role = "external-reference"
            addresses[key] = {
                "kind": "runtime-url",
                "role": role,
                "value": value,
                "path": rel,
            }
        for variable in ADDRESS_VARIABLE.findall(content):
            key = ("environment-variable", variable, rel)
            addresses[key] = {
                "kind": "environment-variable",
                "role": "runtime-configuration",
                "value": variable,
                "path": rel,
            }
        if len(addresses) >= max_items * 2:
            break
    return sorted(
        addresses.values(),
        key=lambda item: (item["kind"], item["value"], item["path"]),
    )[:max_items]


def discover_api_behavior(
    files: list[Path],
    root: Path,
    max_items: int,
) -> list[dict[str, str]]:
    candidates: dict[str, dict[str, str]] = {}
    markers = {
        "route-or-handler": (
            "@router.",
            "@app.",
            "router.get(",
            "router.post(",
            "app.get(",
            "app.post(",
            "@getmapping",
            "@postmapping",
            "urlpatterns",
        ),
        "authorization": (
            "permission",
            "authorize",
            "require_auth",
            "require_session",
            "access control",
        ),
        "schema-or-serializer": (
            "basemodel",
            "serializer",
            "request schema",
            "response schema",
        ),
        "rag-or-retrieval": (
            "embedding",
            "retrieval",
            "vector",
            "guardrail",
            "prompt injection",
        ),
        "integration-or-webhook": (
            "webhook",
            "connector",
            "integration",
        ),
    }
    for path in files:
        if path.suffix.lower() not in SOURCE_SUFFIXES:
            continue
        rel = relative(path, root)
        rel_parts = {part.lower() for part in Path(rel).parts}
        if (
            TEST_NAME.search(path.name)
            or rel_parts & {"test", "tests", "testing_report"}
        ):
            continue
        content = read_text(path, 150_000).lower()
        for kind, tokens in markers.items():
            if any(token in content for token in tokens):
                candidates.setdefault(rel, {"path": rel, "kind": kind})
                break
    return sorted(candidates.values(), key=lambda item: item["path"])[:max_items]


def infer_linked_repository_roles(
    repositories: list[dict[str, object]],
) -> list[dict[str, object]]:
    enriched = []
    role_tokens = {
        "docs": {"docs", "documentation", "handbook"},
        "frontend": {"frontend", "web", "ui"},
        "api": {"api", "backend", "server"},
        "rag": {"rag", "retrieval", "search", "vector"},
        "worker": {"worker", "jobs", "consumer"},
        "integration": {"integration", "connector", "adapter"},
        "sdk": {"sdk", "client"},
        "library": {"shared", "common", "helper", "helpers", "library", "package"},
        "tooling": {"automation", "scripts", "tools", "tooling"},
    }
    for repository in repositories:
        path_tokens = set(
            token
            for part in Path(str(repository["path"])).parts
            for token in re.split(r"[-_. ]+", part.lower())
            if token
        )
        assumed_roles = [
            role
            for role, tokens in role_tokens.items()
            if path_tokens & tokens
        ]
        git_root = repository.get("git_root")
        playbook_candidates = (
            discover_drafts(
                [Path(git_root)],
                [Path(git_root)],
                None,
                None,
            )
            if isinstance(git_root, str)
            else []
        )
        enriched.append(
            {
                **repository,
                "assumed_roles": assumed_roles or ["unknown"],
                "playbook_candidates": playbook_candidates,
            }
        )
    return enriched


def classify_tests_and_interfaces(
    files: list[Path], root: Path, max_items: int
) -> dict[str, list[str]]:
    tests: list[str] = []
    browser_tests: list[str] = []
    api_tests: list[str] = []
    cli_tests: list[str] = []
    service_tests: list[str] = []
    mobile_tests: list[str] = []
    page_objects: list[str] = []
    interfaces: list[str] = []
    instruction_files: list[str] = []
    ci_files: list[str] = []

    for path in files:
        rel = relative(path, root)
        rel_lower = rel.lower()
        if path.name in {"AGENTS.md", "CLAUDE.md"}:
            instruction_files.append(rel)
        if (
            rel_lower.startswith((".github/workflows/", ".circleci/"))
            or path.name
            in {
                ".gitlab-ci.yml",
                "azure-pipelines.yml",
                "Jenkinsfile",
            }
        ):
            ci_files.append(rel)
        if path.suffix.lower() not in SOURCE_SUFFIXES:
            continue
        if INTERFACE_NAME.search(path.name) or any(
            part.lower() in {"routes", "controllers", "handlers", "commands", "workers", "jobs"}
            for part in path.parts
        ):
            interfaces.append(rel)
        if (
            PAGE_OBJECT_NAME.search(path.stem)
            or any(
                part.lower() in {"page-object", "page-objects", "page_objects"}
                for part in path.parts
            )
        ) and not TEST_NAME.search(path.name):
            page_objects.append(rel)
        test_path_signal = any(
            part.lower()
            in {
                "e2e",
                "integration",
                "integration-tests",
                "spec",
                "specs",
                "test",
                "tests",
            }
            for part in Path(rel).parts[:-1]
        )
        if not TEST_NAME.search(path.name) and not test_path_signal:
            continue

        tests.append(rel)
        content = read_text(path, limit=150_000).lower()
        browser_markers = (
            "page.goto(",
            "cy.visit(",
            "webdriver",
            "browser.get(",
            "driver.get(",
        )
        api_markers = (
            "testclient(",
            "client.get(",
            "client.post(",
            "client.put(",
            "client.patch(",
            "client.delete(",
            "status_code",
            "supertest",
            "request(app",
            "mockmvc",
            "httptest.",
            "/api/",
        )
        cli_markers = (
            "clirunner",
            "click.testing",
            "subprocess.run(",
            "commandrunner",
            "invoke_cli",
        )
        service_markers = (
            "webhook",
            "worker",
            "consumer",
            "background job",
            "enqueue",
            "dequeue",
        )
        mobile_markers = (
            "device.launchapp",
            "appium",
            "xctest",
            "espresso",
            "widgettester",
            "flutterdriver",
        )
        if (
            any(part.lower() in {"e2e", "cypress", "playwright"} for part in Path(rel).parts)
            or any(marker in content for marker in browser_markers)
        ):
            browser_tests.append(rel)
        if any(marker in content for marker in api_markers):
            api_tests.append(rel)
        if any(marker in content for marker in cli_markers):
            cli_tests.append(rel)
        if any(marker in content for marker in service_markers):
            service_tests.append(rel)
        if any(marker in content for marker in mobile_markers):
            mobile_tests.append(rel)

    return {
        "test_files": sorted(tests)[:max_items],
        "browser_test_files": sorted(browser_tests)[:max_items],
        "api_test_files": sorted(api_tests)[:max_items],
        "cli_test_files": sorted(cli_tests)[:max_items],
        "service_test_files": sorted(service_tests)[:max_items],
        "mobile_test_files": sorted(mobile_tests)[:max_items],
        "test_directories": sorted(
            {
                Path(test).parent.as_posix()
                for test in tests
                if Path(test).parent.as_posix() != "."
            }
        )[:max_items],
        "page_object_candidates": sorted(page_objects)[:max_items],
        "interface_source_candidates": sorted(interfaces)[:max_items],
        "instruction_files": sorted(instruction_files)[:max_items],
        "ci_files": sorted(ci_files)[:max_items],
    }


def detect_viewport_fork_candidates(
    files: list[Path],
    root: Path,
    max_items: int,
) -> list[dict[str, str]]:
    scored: list[tuple[int, dict[str, str]]] = []
    for path in files:
        if path.suffix.lower() not in VIEWPORT_FORK_SUFFIXES:
            continue
        rel = relative(path, root)
        if _auth_role_path_is_noisy(rel):
            continue
        name_lower = path.name.lower()
        stem_lower = path.stem.lower()
        rel_lower = rel.lower()
        reasons: list[str] = []
        filename_hit = any(
            token in stem_lower or token in name_lower
            for token in ("mobile", "desktop", "responsive", "breakpoint")
        )
        if filename_hit:
            reasons.append("viewport-oriented filename")
        content = read_text(path, limit=120_000)
        content_lower = content.lower()
        for marker, reason in VIEWPORT_FORK_MARKERS:
            if marker in content_lower and reason not in reasons:
                reasons.append(reason)
        if not reasons:
            continue
        # Bare @media in generic CSS is too noisy for Intake. Keep stronger signals.
        if reasons == ["CSS media query"] and not filename_hit:
            continue
        # Test harness matchMedia polyfills are weak Intake clues.
        if (
            reasons == ["matchMedia usage"]
            and ("setup" in stem_lower or "polyfill" in stem_lower or "/test/" in rel_lower)
        ):
            continue
        auth_crossover = any(
            marker in content_lower for marker in VIEWPORT_AUTH_CROSSOVER_MARKERS
        )
        if auth_crossover and "viewport + permission/role fork" not in reasons:
            reasons.insert(0, "viewport + permission/role fork")
        score = 10
        if auth_crossover:
            score += 80
        if any(
            token in rel_lower
            for token in ("/sidebar", "/nav", "/shell", "/header", "/layout")
        ):
            score += 40
        if any(
            token in content_lower
            for token in ("mobilevariant", "desktopvariant", "usemediaquery")
        ):
            score += 25
        if filename_hit:
            score += 5
        # Prefer product features over shared UI primitives.
        if rel_lower.startswith("app/ui/") or "/components/ui/" in rel_lower:
            score -= 20
        scored.append(
            (
                score,
                {
                    "path": rel,
                    "reason": reasons[0],
                },
            )
        )
    scored.sort(key=lambda item: (-item[0], item[1]["path"]))
    return [item for _, item in scored[:max_items]]


def probe_linked_viewport_fork_candidates(
    linked_repositories: list[dict[str, Any]],
    max_items: int,
) -> list[dict[str, str]]:
    merged: list[dict[str, str]] = []
    for linked in linked_repositories:
        git_root = linked.get("git_root") or linked.get("path")
        if not git_root:
            continue
        linked_root = Path(str(git_root))
        if not linked_root.is_dir():
            continue
        rel_prefix = str(linked.get("path") or linked_root.name)
        try:
            files = walk_files(linked_root)
        except OSError:
            continue
        for item in detect_viewport_fork_candidates(files, linked_root, max_items):
            merged.append(
                {
                    **item,
                    "path": f"{rel_prefix}/{item['path']}",
                    "reason": f"linked repo ({item.get('reason')})",
                }
            )
            if len(merged) >= max_items:
                return merged
    return merged


def detect_marker_candidates(
    files: list[Path],
    root: Path,
    max_items: int,
    *,
    markers: tuple[tuple[str, str], ...],
    name_tokens: tuple[str, ...] = (),
    suffixes: set[str] | None = None,
    skip_noisy_paths: bool = False,
) -> list[dict[str, str]]:
    allowed = suffixes or SOURCE_SUFFIXES
    scored: list[tuple[int, dict[str, str]]] = []
    for path in files:
        if path.suffix.lower() not in allowed:
            continue
        rel = relative(path, root)
        if skip_noisy_paths and _auth_role_path_is_noisy(rel):
            continue
        name_lower = path.name.lower()
        stem_lower = path.stem.lower()
        reasons: list[str] = []
        if name_tokens and any(
            token in stem_lower or token in name_lower for token in name_tokens
        ):
            reasons.append("matching filename")
        content = read_text(path, limit=120_000).lower()
        for marker, reason in markers:
            if marker in content and reason not in reasons:
                reasons.append(reason)
        if not reasons:
            continue
        score = 10
        if any(token in rel.lower() for token in ("/auth", "/roles", "permission")):
            score += 40
        if reasons[0] == "matching filename":
            score += 10
        scored.append((score, {"path": rel, "reason": reasons[0]}))
    scored.sort(key=lambda item: (-item[0], item[1]["path"]))
    return [item for _, item in scored[:max_items]]


def _auth_role_slug(raw: str) -> str:
    return re.sub(r"[_-]+", " ", raw).strip().lower()


def _auth_role_display(raw: str) -> str:
    normalized = re.sub(r"[_-]+", " ", raw).strip()
    if not normalized:
        return ""
    if " " in normalized or normalized != normalized.lower():
        # Preserve intentional Title Case / multi-word names.
        if any(ch.isupper() for ch in normalized[1:]):
            return normalized
        return " ".join(part[:1].upper() + part[1:] for part in normalized.split())
    return normalized[:1].upper() + normalized[1:]


def _auth_role_acceptable(raw: str, *, require_known: bool) -> bool:
    slug = _auth_role_slug(raw)
    if not slug or len(slug) < 2:
        return False
    if slug in AUTH_CHAT_ROLE_LABELS or slug in AUTH_ROLE_LABEL_STOPWORDS:
        return False
    if require_known and slug not in AUTH_KNOWN_ROLE_SLUGS:
        return False
    return True


def _collect_auth_role_label(
    labels: list[str],
    seen: set[str],
    raw: str,
    *,
    require_known: bool,
) -> None:
    if not _auth_role_acceptable(raw, require_known=require_known):
        return
    slug = _auth_role_slug(raw)
    if slug in seen:
        return
    seen.add(slug)
    labels.append(_auth_role_display(raw))


def _labels_from_definition_block(block: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for match in re.finditer(r"['\"]([A-Za-z_][A-Za-z0-9_ -]{1,40})['\"]", block):
        _collect_auth_role_label(
            found, seen, match.group(1), require_known=False
        )
    for match in re.finditer(
        r"\b([A-Z][A-Za-z0-9]+)\s*(?:=|,|}|\n)",
        block,
    ):
        _collect_auth_role_label(
            found, seen, match.group(1), require_known=True
        )
    return found


def extract_auth_role_labels(content: str) -> list[str]:
    labels: list[str] = []
    seen: set[str] = set()

    for pattern in AUTH_ROLE_DEFINITION_PATTERNS:
        for match in pattern.finditer(content):
            for label in _labels_from_definition_block(match.group(1)):
                slug = _auth_role_slug(label)
                if slug in seen:
                    continue
                seen.add(slug)
                labels.append(label)
                if len(labels) >= 12:
                    return labels

    for match in AUTH_ROLE_FACTORY_PATTERN.finditer(content):
        display_name, tier = match.group(1), match.group(2)
        _collect_auth_role_label(labels, seen, display_name, require_known=False)
        _collect_auth_role_label(labels, seen, tier, require_known=True)
        if len(labels) >= 12:
            return labels

    for pattern in AUTH_ROLE_WEAK_PATTERNS:
        for match in pattern.finditer(content):
            _collect_auth_role_label(
                labels, seen, match.group(1), require_known=True
            )
            if len(labels) >= 12:
                return labels
    return labels


def _auth_role_path_is_noisy(rel: str) -> bool:
    lowered = rel.replace("\\", "/").lower()
    return any(part in lowered for part in AUTH_ROLE_NOISE_PATH_PARTS)


def detect_auth_role_candidates(
    files: list[Path],
    root: Path,
    max_items: int,
) -> list[dict[str, Any]]:
    scored: list[tuple[int, dict[str, Any]]] = []
    for path in files:
        suffix = path.suffix.lower()
        is_contract_json = suffix == ".json" and any(
            token in path.name.lower()
            for token in ("openapi", "swagger", "schema", "api")
        )
        if suffix not in SOURCE_SUFFIXES and not is_contract_json:
            continue
        rel = relative(path, root)
        if _auth_role_path_is_noisy(rel):
            continue
        name_lower = path.name.lower()
        stem_lower = path.stem.lower()
        reasons: list[str] = []
        filename_hit = any(
            token in stem_lower or token in name_lower
            for token in ("role", "roles", "permission", "rbac", "tier")
        )
        if filename_hit:
            reasons.append("matching filename")
        content = read_text(path, limit=120_000)
        content_lower = content.lower()
        for marker, reason in AUTH_ROLE_MARKERS:
            if marker in content_lower and reason not in reasons:
                reasons.append(reason)
        labels = extract_auth_role_labels(content)
        if not labels:
            # Filename / weak marker alone is not enough — that produced
            # Suspend/View/Assistant/Fixer noise without real personas.
            continue
        if not reasons:
            reasons.append("named role definition")
        # Prefer definition-rich auth/roles files over incidental mentions.
        score = len(labels) * 10
        if any(token in rel.lower() for token in ("/auth", "/roles", "roletier", "openapi")):
            score += 50
        if filename_hit:
            score += 10
        scored.append(
            (
                score,
                {
                    "path": rel,
                    "reason": reasons[0],
                    "labels": labels,
                },
            )
        )
    scored.sort(key=lambda item: (-item[0], item[1]["path"]))
    return [item for _, item in scored[:max_items]]


def probe_linked_auth_role_candidates(
    linked_repositories: list[dict[str, Any]],
    max_items: int,
) -> list[dict[str, Any]]:
    """Workspace wrappers often keep product code in nested git checkouts.

    Parent `git ls-files` misses those trees, so probe linked repos lightly for
    product role names when the wrapper itself has none.
    """
    merged: list[dict[str, Any]] = []
    for linked in linked_repositories:
        git_root = linked.get("git_root") or linked.get("path")
        if not git_root:
            continue
        linked_root = Path(str(git_root))
        if not linked_root.is_dir():
            continue
        rel_prefix = str(linked.get("path") or linked_root.name)
        try:
            files = walk_files(linked_root)
        except OSError:
            continue
        for item in detect_auth_role_candidates(files, linked_root, max_items):
            merged.append(
                {
                    **item,
                    "path": f"{rel_prefix}/{item['path']}",
                    "reason": f"linked repo ({item.get('reason')})",
                }
            )
            if len(merged) >= max_items:
                return merged
    return merged


def probe_linked_auth_gate_candidates(
    linked_repositories: list[dict[str, Any]],
    max_items: int,
) -> list[dict[str, str]]:
    merged: list[dict[str, str]] = []
    for linked in linked_repositories:
        git_root = linked.get("git_root") or linked.get("path")
        if not git_root:
            continue
        linked_root = Path(str(git_root))
        if not linked_root.is_dir():
            continue
        rel_prefix = str(linked.get("path") or linked_root.name)
        try:
            files = walk_files(linked_root)
        except OSError:
            continue
        for item in detect_marker_candidates(
            files,
            linked_root,
            max_items,
            markers=AUTH_GATE_MARKERS,
            name_tokens=("auth", "permission", "guard", "policy"),
            skip_noisy_paths=True,
        ):
            merged.append(
                {
                    **item,
                    "path": f"{rel_prefix}/{item['path']}",
                    "reason": f"linked repo ({item.get('reason')})",
                }
            )
            if len(merged) >= max_items:
                return merged
    return merged


def merge_auth_role_candidates(
    primary: list[dict[str, Any]],
    linked: list[dict[str, Any]],
    max_items: int,
) -> list[dict[str, Any]]:
    if primary:
        return primary[:max_items]
    return linked[:max_items]


def detect_project_signals(
    project_text: str,
    files: list[Path],
    root: Path,
) -> list[dict[str, Any]]:
    signals: dict[str, list[str]] = {
        "frontend": [],
        "api": [],
        "cli": [],
        "service": [],
        "worker": [],
        "mobile": [],
        "rag": [],
        "library": [],
        "sdk": [],
        "integration": [],
        "extension": [],
        "data": [],
        "tooling": [],
    }
    token_groups = {
        "frontend": (
            '"react"',
            "next",
            "nuxt",
            "svelte",
            "vue",
            "angular",
            "solid-js",
        ),
        "api": (
            "fastapi",
            "flask",
            "django",
            "express",
            "@nestjs",
            "fastify",
            "spring-boot",
            "aspnetcore",
            "gin-gonic",
            "actix-web",
            "axum",
            "rails",
        ),
        "cli": ("commander", "click", "typer", "argparse", "cobra", "clap"),
        "service": ("celery", "bullmq", "sidekiq", "kafka", "rabbitmq", "temporal"),
        "worker": ("celery", "bullmq", "sidekiq", "kafka", "rabbitmq", "temporal"),
        "mobile": ("react-native", "flutter", "androidx", "swiftui"),
        "rag": (
            "langchain",
            "llama-index",
            "llamaindex",
            "pgvector",
            "pinecone",
            "weaviate",
            "chromadb",
            "qdrant",
            "milvus",
        ),
        "sdk": ("sdk", "api-client", "openapi-generator"),
        "integration": ("webhook", "connector", "integration"),
        "extension": ("vscode", "browser-extension", "webextension"),
        "data": ("airflow", "dbt", "dagster", "prefect"),
    }
    for category, tokens in token_groups.items():
        for token in tokens:
            if token in project_text:
                add_signal(signals, category, f"{token} project dependency")
                break
    if any(path.name in {"AndroidManifest.xml", "pubspec.yaml"} for path in files):
        add_signal(signals, "mobile", "mobile project manifest")
    path_tokens = {
        token
        for path in files
        for part in path.relative_to(root).parts
        for token in re.split(r"[-_. ]+", part.lower())
        if token
    }
    if path_tokens & {"rag", "retrieval", "embeddings", "vectors", "guardrails"}:
        add_signal(signals, "rag", "RAG, retrieval, embedding, vector, or guardrail source")
    if path_tokens & {"integrations", "connectors", "adapters", "webhooks"}:
        add_signal(signals, "integration", "integration, connector, adapter, or webhook source")
    if path_tokens & {"workers", "jobs", "consumers", "queues"}:
        add_signal(signals, "worker", "worker, job, consumer, or queue source")
    if root.name.lower() in {
        "common",
        "helper",
        "helpers",
        "lib",
        "libs",
        "library",
        "packages",
        "shared",
        "utils",
    }:
        add_signal(signals, "library", "helper, shared, or library component name")
    if root.name.lower() in {"sdk", "client", "api-client"}:
        add_signal(signals, "sdk", "SDK or client component name")
    if any(path.name in {"dbt_project.yml", "dbt_project.yaml"} for path in files):
        add_signal(signals, "data", "data project manifest")
    if root.name.lower() in {"scripts", "tools", "tooling", "automation"}:
        add_signal(signals, "tooling", "tooling or automation component name")
    if '"exports"' in project_text or '"types"' in project_text:
        add_signal(signals, "library", "package exports or type declarations")
    source_probe = "\n".join(
        read_text(path, 60_000).lower()
        for path in files[:300]
        if path.suffix.lower() in SOURCE_SUFFIXES
    )
    if any(
        marker in source_probe
        for marker in (
            "argparse.argumentparser",
            "click.command",
            "typer.typer",
            "commander.command",
        )
    ):
        add_signal(signals, "cli", "command registration in executable source")
    if any(
        marker in source_probe
        for marker in (
            "@router.get",
            "@router.post",
            "@app.get",
            "@app.post",
            "fastapi(",
            "express()",
        )
    ):
        add_signal(signals, "api", "route registration in application source")
    if any(
        marker in source_probe
        for marker in (
            "retrieve_context",
            "vector_store",
            "embedding",
            "prompt injection",
            "guardrail",
        )
    ):
        add_signal(signals, "rag", "RAG or retrieval behavior in application source")
    return [
        {"name": name, "signals": reasons}
        for name, reasons in signals.items()
        if reasons
    ]


def select_surface(
    override: str,
    classified: dict[str, list[str]],
    contracts: list[str],
    project_signals: list[dict[str, Any]],
) -> str:
    if override != "auto":
        return override
    return surface_profile(classified, contracts, project_signals)["primary_surface"]


def surface_profile(
    classified: dict[str, list[str]],
    contracts: list[str],
    project_signals: list[dict[str, Any]],
) -> dict[str, Any]:
    signal_names = {signal["name"] for signal in project_signals}
    scores: dict[str, float] = {}
    if classified["browser_test_files"]:
        scores["frontend"] = 0.95
    elif "frontend" in signal_names:
        scores["frontend"] = 0.72
    if classified["api_test_files"] or contracts:
        scores["api"] = 0.95
    elif "api" in signal_names:
        scores["api"] = 0.72
    if classified["cli_test_files"]:
        scores["cli"] = 0.92
    elif "cli" in signal_names:
        scores["cli"] = 0.7
    if classified["service_test_files"]:
        scores["service"] = 0.9
    elif "service" in signal_names:
        scores["service"] = 0.7
    for name, confidence in {
        "worker": 0.78,
        "rag": 0.82,
        "library": 0.68,
        "sdk": 0.75,
        "integration": 0.76,
        "extension": 0.76,
        "data": 0.74,
        "tooling": 0.7,
    }.items():
        if name in signal_names:
            scores[name] = confidence
    if contracts:
        scores["contracts"] = 0.9
    if classified["mobile_test_files"]:
        scores["mobile"] = 0.92
    elif "mobile" in signal_names:
        scores["mobile"] = 0.72
    surfaces = sorted(scores, key=lambda name: (-scores[name], name))
    primary = "unknown"
    if "frontend" in scores and "api" in scores:
        primary = "fullstack"
    elif surfaces:
        primary = surfaces[0]
    return {
        "surfaces": surfaces or ["unknown"],
        "surface_confidence": scores,
        "primary_surface": primary,
    }


def detect_test_commands(
    root: Path,
    files: list[Path],
    frameworks: list[dict[str, Any]],
) -> dict[str, str]:
    commands: dict[str, str] = {}
    package_json = root / "package.json"
    if package_json.is_file():
        try:
            data = json.loads(package_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        scripts = data.get("scripts", {})
        if isinstance(scripts, dict):
            keywords = (
                "test",
                "e2e",
                "playwright",
                "cypress",
                "selenium",
                "storybook",
                "integration",
                "contract",
            )
            commands.update(
                {
                    str(key): str(value)
                    for key, value in scripts.items()
                    if any(
                        word in str(key).lower() or word in str(value).lower()
                        for word in keywords
                    )
                }
            )

    names = {relative(path, root) for path in files}
    framework_names = {item["name"] for item in frameworks}
    if "pytest" in framework_names:
        commands.setdefault("pytest", "pytest")
    if "unittest" in framework_names:
        commands.setdefault("unittest", "python -m unittest")
    if "go-test" in framework_names:
        commands.setdefault("go-test", "go test ./...")
    if "cargo-test" in framework_names:
        commands.setdefault("cargo-test", "cargo test")
    if "rspec" in framework_names:
        commands.setdefault("rspec", "bundle exec rspec")
    if "junit" in framework_names and "mvnw" in names:
        commands.setdefault("junit", "./mvnw test")
    if "junit" in framework_names and "gradlew" in names:
        commands.setdefault("junit", "./gradlew test")
    if "xunit" in framework_names:
        commands.setdefault("dotnet-test", "dotnet test")
    if "flutter-test" in framework_names:
        commands.setdefault("flutter-test", "flutter test")
    if "bats" in framework_names:
        commands.setdefault("bats", "bats tests")
    makefile = root / "Makefile"
    if makefile.is_file():
        make_text = read_text(makefile, 100_000)
        for target in re.findall(r"^([A-Za-z0-9_.-]*(?:test|check)[A-Za-z0-9_.-]*):", make_text, re.M):
            commands.setdefault(f"make-{target}", f"make {target}")
    for name in ("Justfile", "justfile"):
        justfile = root / name
        if justfile.is_file():
            just_text = read_text(justfile, 100_000)
            for recipe in re.findall(
                r"^([A-Za-z0-9_-]*(?:test|check)[A-Za-z0-9_-]*):",
                just_text,
                re.M,
            ):
                commands.setdefault(f"just-{recipe}", f"just {recipe}")
    return commands


def discover_component_candidates(
    root: Path,
    files: list[Path],
    args: argparse.Namespace,
    source_id: str,
) -> list[dict[str, Any]]:
    candidates = sorted(
        {
            path.parent
            for path in files
            if path.name in MANIFEST_NAMES or path.suffix.lower() == ".csproj"
        }
    )
    nested = [path for path in candidates if path != root]
    component_roots = nested or [root]
    components: list[dict[str, Any]] = []
    for component_root in component_roots:
        component_files = [
            path
            for path in files
            if path == component_root or path.is_relative_to(component_root)
        ]
        project_text, _ = select_manifests(component_files, component_root)
        frameworks = detect_test_frameworks(
            component_files,
            project_text,
            component_root,
        )
        classified = classify_tests_and_interfaces(
            component_files,
            component_root,
            args.max_items,
        )
        contract_evidence = detect_contract_evidence(
            component_files,
            component_root,
            args.max_items,
        )
        contracts = [
            item["path"]
            for item in contract_evidence
            if item["is_contract_artifact"]
        ]
        signals = detect_project_signals(project_text, component_files, component_root)
        profile = surface_profile(classified, contracts, signals)
        if args.product_surface != "auto":
            profile = {
                "surfaces": [args.product_surface],
                "surface_confidence": {args.product_surface: 1.0},
                "primary_surface": args.product_surface,
            }
        relative_root = relative(component_root, root)
        components.append(
            {
                "component_id": (
                    source_id if relative_root == "." else f"{source_id}:{relative_root}"
                ),
                "source_id": source_id,
                "path": relative_root,
                **profile,
                "frameworks": [item["name"] for item in frameworks],
                "test_files": classified["test_files"],
                "test_commands": detect_test_commands(
                    component_root,
                    component_files,
                    frameworks,
                ),
                "contract_candidates": contracts[: args.max_items],
                "contract_evidence": contract_evidence,
                "viewport_fork_candidates": detect_viewport_fork_candidates(
                    component_files,
                    component_root,
                    args.max_items,
                ),
                "auth_role_candidates": detect_auth_role_candidates(
                    component_files,
                    component_root,
                    args.max_items,
                ),
                "auth_gate_candidates": detect_marker_candidates(
                    component_files,
                    component_root,
                    args.max_items,
                    markers=AUTH_GATE_MARKERS,
                    name_tokens=("auth", "permission", "guard", "policy"),
                    skip_noisy_paths=True,
                ),
            }
        )
    return components


def discover_repository(
    root: Path,
    args: argparse.Namespace,
    source_id: str,
) -> dict[str, Any]:
    files = walk_files(root)
    project_text, manifests = select_manifests(files, root)
    frameworks = detect_test_frameworks(files, project_text, root)
    classified = classify_tests_and_interfaces(files, root, args.max_items)
    contract_evidence = detect_contract_evidence(files, root, args.max_items)
    contracts = [
        item["path"]
        for item in contract_evidence
        if item["is_contract_artifact"]
    ]
    project_signals = detect_project_signals(project_text, files, root)
    surface = select_surface(args.product_surface, classified, contracts, project_signals)
    profile = surface_profile(classified, contracts, project_signals)
    if args.product_surface != "auto":
        profile = {
            "surfaces": [args.product_surface],
            "surface_confidence": {args.product_surface: 1.0},
            "primary_surface": args.product_surface,
        }
    if "frontend" in profile["surfaces"]:
        for item in contract_evidence:
            item["repository_context"] = "frontend-contract-copy-or-codegen-input"
    elif profile["primary_surface"] in {"api", "service"}:
        for item in contract_evidence:
            item["repository_context"] = "backend-or-service-contract"
    unclassified = sorted(
        {
            relative(path, root)
            for path in files
            if (
                any(
                    part.lower()
                    in {"e2e", "integration", "spec", "specs", "test", "tests"}
                    for part in path.parts
                )
                or TEST_NAME.search(path.name)
            )
            and path.suffix.lower() not in SOURCE_SUFFIXES
        }
    )[: args.max_items]
    linked_repositories = infer_linked_repository_roles(
        discover_nested_git_repositories(root)
    )
    # Nested members are expanded into their own repositories before this runs.
    # Keep linked_repository_candidates for residual metadata only — do not use
    # them as a fallback scan of "the frontend somewhere under the wrapper".
    auth_roles = detect_auth_role_candidates(files, root, args.max_items)
    auth_gates = detect_marker_candidates(
        files,
        root,
        args.max_items,
        markers=AUTH_GATE_MARKERS,
        name_tokens=("auth", "permission", "guard", "policy"),
        skip_noisy_paths=True,
    )
    viewport_forks = detect_viewport_fork_candidates(files, root, args.max_items)
    return {
        "source_id": source_id,
        "root": str(root),
        "languages": detect_languages(files),
        "selected_surface": profile["primary_surface"] if args.product_surface == "auto" else surface,
        **profile,
        "test_framework_candidates": frameworks,
        "project_signals": project_signals,
        "project_manifests": manifests,
        "contract_candidates": contracts[: args.max_items],
        "contract_evidence": contract_evidence,
        "address_candidates": discover_addresses(
            files,
            root,
            contract_evidence,
            args.max_items,
        ),
        "documentation_candidates": discover_documentation_candidates(
            files,
            root,
            args.max_items,
        ),
        "prior_work_candidates": discover_prior_work(
            files,
            root,
            args.max_items,
        ),
        "scope_warnings": discover_scope_warnings(
            files,
            root,
            args.max_items,
        ),
        "api_behavior_candidates": discover_api_behavior(
            files,
            root,
            args.max_items,
        ),
        "repository_identity": git_repository_identity(root),
        "linked_repository_candidates": linked_repositories,
        "test_commands": detect_test_commands(root, files, frameworks),
        "unclassified_test_candidates": unclassified,
        "viewport_fork_candidates": viewport_forks,
        "auth_role_candidates": auth_roles,
        "auth_gate_candidates": auth_gates,
        "recommended_next_probes": (
            []
            if frameworks or classified["test_files"]
            else [
                "Inspect repository instructions and CI workflows.",
                "Inspect task-runner files and executable scripts for test commands.",
                "Identify actions followed by observable assertions.",
            ]
        ),
        "component_candidates": discover_component_candidates(
            root,
            files,
            args,
            source_id,
        ),
        **classified,
    }


def discover_docs(
    sources: list[tuple[str, Path]],
    max_items: int,
) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    for source_id, root in sources:
        if not root.exists():
            reports.append(
                {
                    "source_id": source_id,
                    "root": str(root),
                    "error": "path does not exist",
                    "files": [],
                }
            )
            continue
        files = [root] if root.is_file() else walk_files(root)
        contract_evidence = detect_contract_evidence(
            files,
            root if root.is_dir() else root.parent,
            max_items,
        )
        docs = [
            relative(path, root if root.is_dir() else root.parent)
            for path in files
            if path.is_file() and path.suffix.lower() in DOC_SUFFIXES
        ]
        reports.append(
            {
                "source_id": source_id,
                "root": str(root),
                "files": sorted(docs)[:max_items],
                "repository_identity": git_repository_identity(
                    root if root.is_dir() else root.parent
                ),
                "contract_evidence": contract_evidence,
                "address_candidates": discover_addresses(
                    files,
                    root if root.is_dir() else root.parent,
                    contract_evidence,
                    max_items,
                ),
                "prior_work_candidates": discover_prior_work(
                    files,
                    root if root.is_dir() else root.parent,
                    max_items,
                ),
            }
        )
    return reports


def parse_source_refs(raw_refs: list[str]) -> dict[str, str]:
    refs: dict[str, str] = {}
    for raw in raw_refs:
        if "=" not in raw:
            raise ValueError("source ref must use SOURCE_ID=REF")
        source_id, ref = raw.split("=", 1)
        source_id = source_id.strip().lower()
        ref = ref.strip()
        if not source_id or not ref:
            raise ValueError("source ref must use SOURCE_ID=REF")
        refs[source_id] = ref
    return refs


def collect_source_specs(args: argparse.Namespace) -> list[SourceSpec]:
    specs = [
        *(parse_source_spec(raw, "code") for raw in args.source),
        *(parse_source_spec(raw, "docs") for raw in args.docs_source),
        *legacy_specs(args.code_repo, args.docs_path),
    ]
    if not specs:
        raise ValueError("provide at least one --source, --docs-source, or --code-repo")
    ensure_unique_sources(specs)
    refs = parse_source_refs(args.source_ref)
    unknown_refs = sorted(set(refs) - {spec.source_id for spec in specs})
    if unknown_refs:
        raise ValueError(f"source refs name unknown sources: {', '.join(unknown_refs)}")
    return [
        SourceSpec(
            source_id=spec.source_id,
            locator=spec.locator,
            kind=spec.kind,
            ref=refs.get(spec.source_id),
        )
        for spec in specs
    ]


def inspect_playbook_state(directory: Path) -> dict[str, Any] | None:
    state_path = directory / ".product-playbook-state.json"
    if not state_path.is_file():
        return None
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"path": state_path.name, "valid_json": False}
    if not isinstance(state, dict):
        return {"path": state_path.name, "valid_json": False}
    sources = state.get("sources")
    scenarios = state.get("scenarios")
    return {
        "path": state_path.name,
        "valid_json": True,
        "managed_by": state.get("managed_by"),
        "schema_version": state.get("schema_version"),
        "source_ids": sorted(sources) if isinstance(sources, dict) else [],
        "scenario_count": len(scenarios) if isinstance(scenarios, dict) else 0,
    }


def inspect_draft_candidate(
    path: Path,
    *,
    allow_weak_match: bool = False,
) -> dict[str, Any] | None:
    directory = path.parent if path.is_file() else path
    if not directory.is_dir():
        return None
    markdown = sorted(directory.glob("*.md"))
    if not markdown:
        return None
    combined = "\n".join(read_text(item, 200_000) for item in markdown)
    scenario_count = len(SCENARIO_HEADING.findall(combined))
    has_results = (directory / "results-template.md").is_file()
    has_hub = (directory / "README.md").is_file()
    playbook_language = "playbook" in combined.lower() or "manual test" in combined.lower()
    strong_match = bool(scenario_count or has_results)
    weak_match = bool(playbook_language)
    if not (strong_match or (allow_weak_match and weak_match)):
        return None
    return {
        "path": str(directory.resolve()),
        "markdown_files": len(markdown),
        "scenario_count": scenario_count,
        "has_readme": has_hub,
        "has_results_template": has_results,
        "state": inspect_playbook_state(directory),
        "legacy_state_found": (directory / ".product-playbook").is_dir(),
    }


def discover_drafts(
    roots: list[Path],
    docs_paths: list[Path],
    explicit_draft: str | None,
    output_dir: str | None,
) -> list[dict[str, Any]]:
    candidates: dict[str, dict[str, Any]] = {}
    requested: list[tuple[Path, bool]] = []
    if explicit_draft:
        requested.append((Path(explicit_draft).expanduser().resolve(), True))
    if output_dir:
        requested.append((Path(output_dir).expanduser().resolve(), False))
    for root in roots:
        requested.extend(
            (root / candidate, False) for candidate in CONVENTIONAL_DRAFT_DIRS
        )
    for root in [*roots, *docs_paths]:
        if not root.is_dir():
            continue
        for readme in (
            file for file in walk_files(root, max_depth=5) if file.name == "README.md"
        ):
            try:
                depth = len(readme.parent.relative_to(root).parts)
            except ValueError:
                continue
            if depth <= 4:
                requested.append((readme.parent, False))

    for path, allow_weak_match in requested:
        report = inspect_draft_candidate(path, allow_weak_match=allow_weak_match)
        if report:
            candidates[report["path"]] = report
    return sorted(candidates.values(), key=lambda item: item["path"])


def main() -> int:
    args = parse_args()
    if args.max_items < 1:
        raise SystemExit("--max-items must be positive")

    try:
        specs = collect_source_specs(args)
        needs_workspace = any(is_remote_locator(spec.locator) for spec in specs)
        workspace = (
            Path(args.workspace_dir).expanduser().resolve()
            if args.workspace_dir
            else create_workspace()
            if needs_workspace
            else None
        )
        acquired = [acquire_source(spec, workspace) for spec in specs]
    except ValueError as error:
        raise SystemExit(str(error)) from error

    code_sources = [source for source in acquired if source.kind == "code"]
    docs_sources = [source for source in acquired if source.kind == "docs"]
    acquired, workspace_expansions = expand_acquired_sources(acquired)
    code_sources = [source for source in acquired if source.kind == "code"]
    docs_sources = [source for source in acquired if source.kind == "docs"]
    code_roots = [source.root for source in code_sources]
    docs_paths = [source.root for source in docs_sources]

    repositories = [
        {
            **discover_repository(source.root, args, source.source_id),
            "locator_type": source.locator_type,
            "portable_locator": source.portable_locator,
            "revision": source.revision,
        }
        for source in code_sources
    ]
    framework_names = sorted(
        {
            candidate["name"]
            for repository in repositories
            for candidate in repository["test_framework_candidates"]
        }
    )
    framework_override = [
        item.strip().lower()
        for item in args.test_framework.split(",")
        if item.strip()
    ]
    selected_frameworks = (
        framework_names
        if args.test_framework.lower() == "auto"
        else framework_override
    )
    for repository in repositories:
        repository["selected_frameworks"] = (
            [candidate["name"] for candidate in repository["test_framework_candidates"]]
            if args.test_framework.lower() == "auto"
            else selected_frameworks
        )
    drafts = discover_drafts(
        code_roots, docs_paths, args.draft_path, args.output_dir
    )
    linked_drafts = [
        {
            **draft,
            "linked_from_source_id": repository["source_id"],
            "linked_repository_path": linked["path"],
        }
        for repository in repositories
        for linked in repository.get("linked_repository_candidates", [])
        for draft in linked.get("playbook_candidates", [])
    ]
    if args.draft_path:
        explicit_draft = Path(args.draft_path).expanduser().resolve()
        explicit_directory = explicit_draft.parent if explicit_draft.is_file() else explicit_draft
        if str(explicit_directory) not in {item["path"] for item in drafts}:
            raise SystemExit(
                "explicit draft path is missing or does not contain recognizable playbook "
                f"Markdown: {explicit_draft}"
            )
    explicit_output = Path(args.output_dir).expanduser().resolve() if args.output_dir else None
    multi_evidence = (
        len(code_roots) > 1
        or len(docs_paths) > 0
        or bool(workspace_expansions)
    )

    if explicit_output:
        recommended_output: str | None = str(explicit_output)
        output_decision = "explicit_output_dir"
        ask_before_write = False
    elif args.draft_path:
        draft_path = Path(args.draft_path).expanduser().resolve()
        recommended_output = str(draft_path.parent if draft_path.is_file() else draft_path)
        output_decision = "explicit_draft_path"
        ask_before_write = False
    elif len(drafts) == 1:
        recommended_output = drafts[0]["path"]
        output_decision = "reuse_unique_draft"
        ask_before_write = False
    elif len(drafts) > 1:
        recommended_output = None
        output_decision = "ask_which_draft"
        ask_before_write = True
    elif len(linked_drafts) == 1:
        recommended_output = linked_drafts[0]["path"]
        output_decision = "confirm_linked_draft"
        ask_before_write = True
    elif len(linked_drafts) > 1:
        recommended_output = None
        output_decision = "ask_which_linked_draft"
        ask_before_write = True
    elif (
        len(code_sources) == 1
        and code_sources[0].locator_type == "local"
        and not docs_paths
        and not workspace_expansions
    ):
        recommended_output = str(code_roots[0] / "docs" / "playbook")
        output_decision = "default_single_code_repo"
        ask_before_write = False
    else:
        recommended_output = None
        output_decision = "ask_output_dir"
        ask_before_write = True

    if args.draft_path or (len(drafts) == 1 and not ask_before_write):
        mode = "reconcile"
    elif ask_before_write:
        mode = "ask"
    elif drafts:
        mode = "reconcile"
    else:
        mode = "create"

    documentation_reports = discover_docs(
        [(source.source_id, source.root) for source in docs_sources],
        args.max_items,
    )
    repository_by_source = {
        repository["source_id"]: repository for repository in repositories
    }
    docs_by_source = {
        report["source_id"]: report for report in documentation_reports
    }
    source_addresses = []
    for source in acquired:
        detail = (
            repository_by_source.get(source.source_id)
            if source.kind == "code"
            else docs_by_source.get(source.source_id)
        )
        source_addresses.append(
            {
                "source_id": source.source_id,
                "kind": source.kind,
                "local_root": str(source.root),
                "supplied_locator_type": source.locator_type,
                "supplied_remote": source.portable_locator,
                "repository_identity": (
                    detail.get("repository_identity")
                    if isinstance(detail, dict)
                    else git_repository_identity(source.root)
                ),
            }
        )
    prior_work_candidates: list[dict[str, Any]] = [
        {
            "kind": "playbook-draft",
            **draft,
        }
        for draft in drafts
    ]
    prior_work_candidates.extend(
        {
            "kind": "linked-playbook-draft",
            **draft,
        }
        for draft in linked_drafts
    )
    for repository in repositories:
        prior_work_candidates.extend(
            {
                "source_id": repository["source_id"],
                **candidate,
            }
            for candidate in repository["prior_work_candidates"]
        )
    for docs_report in documentation_reports:
        prior_work_candidates.extend(
            {
                "source_id": docs_report["source_id"],
                **candidate,
            }
            for candidate in docs_report.get("prior_work_candidates", [])
        )
    continuation = (
        "continue_unique_playbook"
        if len(drafts) == 1
        else "confirm_and_continue_linked_playbook"
        if len(linked_drafts) == 1
        else "choose_authoritative_playbook"
        if len(drafts) > 1 or len(linked_drafts) > 1
        else "review_prior_work_then_create"
        if prior_work_candidates
        else "create_new_playbook"
    )

    report: dict[str, Any] = {
        "sources": [
            {
                "source_id": source.source_id,
                "kind": source.kind,
                "root": str(source.root),
                "locator_type": source.locator_type,
                "portable_locator": source.portable_locator,
                "revision": source.revision,
                "cleanup_required": source.cleanup_required,
            }
            for source in acquired
        ],
        "workspace_expansions": workspace_expansions,
        "source_addresses": source_addresses,
        "repositories": repositories,
        "documentation": documentation_reports,
        "selected_frameworks": selected_frameworks or ["unknown"],
        "existing_playbook_candidates": drafts,
        "linked_playbook_candidates": linked_drafts,
        "prior_work_candidates": prior_work_candidates[: args.max_items],
        "continuation_suggestion": continuation,
        "evidence_summary": {
            "contract_candidates": sum(
                len(repository["contract_candidates"]) for repository in repositories
            )
            + sum(
                sum(
                    1
                    for item in report.get("contract_evidence", [])
                    if item.get("is_contract_artifact")
                )
                for report in documentation_reports
            ),
            "contract_related_evidence": sum(
                len(repository["contract_evidence"]) for repository in repositories
            )
            + sum(
                len(report.get("contract_evidence", []))
                for report in documentation_reports
            ),
            "address_candidates": sum(
                len(repository["address_candidates"]) for repository in repositories
            )
            + sum(
                len(report.get("address_candidates", []))
                for report in documentation_reports
            ),
            "api_behavior_candidates": sum(
                len(repository["api_behavior_candidates"]) for repository in repositories
            ),
            "documentation_candidates": sum(
                len(repository["documentation_candidates"]) for repository in repositories
            )
            + sum(len(report.get("files", [])) for report in documentation_reports),
            "prior_work_candidates": len(prior_work_candidates),
            "linked_repository_candidates": sum(
                len(repository["linked_repository_candidates"])
                for repository in repositories
            ),
            "scope_warnings": sum(
                len(repository["scope_warnings"]) for repository in repositories
            ),
            "viewport_fork_candidates": sum(
                len(repository.get("viewport_fork_candidates", []))
                for repository in repositories
            ),
            "auth_role_candidates": sum(
                len(repository.get("auth_role_candidates", []))
                for repository in repositories
            ),
            "auth_gate_candidates": sum(
                len(repository.get("auth_gate_candidates", []))
                for repository in repositories
            ),
        },
        "mode_suggestion": mode,
        "output_decision": output_decision,
        "ask_before_write": ask_before_write,
        "recommended_output_dir": recommended_output,
        "multi_evidence_roots": multi_evidence,
        "notes": [],
    }
    cleanup_roots = sorted(
        {
            str(source.root)
            for source in acquired
            if source.cleanup_required
        }
    )
    report["cleanup_paths"] = cleanup_roots
    report["components"] = [
        {
            **component,
            "frameworks": (
                component["frameworks"]
                if args.test_framework.lower() == "auto"
                else selected_frameworks
            ),
        }
        for repository in repositories
        for component in repository["component_candidates"]
    ]
    if output_decision == "ask_which_draft":
        report["notes"].append(
            "Multiple playbook drafts found. Ask which draft is authoritative before writing. "
            "Never merge drafts automatically."
        )
    if output_decision == "ask_output_dir":
        report["notes"].append(
            "Destination is ambiguous or the only code source is a temporary remote checkout. "
            "Ask for output_dir before writing. Reuse that same path on later runs so journeys "
            "reconcile into one product playbook. Suggest a shape like <docs-repo>/playbook only as "
            "an example. Do not invent a repository name."
        )
    if output_decision == "confirm_linked_draft":
        report["notes"].append(
            "One playbook was found in a linked repository that was not supplied as a source. "
            "Ask whether that repository is the canonical documentation repository and whether to "
            "continue the discovered path before writing."
        )
    if output_decision == "ask_which_linked_draft":
        report["notes"].append(
            "Several playbooks were found in linked repositories. Ask which repository and path are "
            "canonical before writing."
        )
    if output_decision == "default_single_code_repo":
        report["notes"].append(
            "No existing draft found. Portable default is <code-repo>/docs/playbook unless the user "
            "supplies output_dir."
        )
    if output_decision == "reuse_unique_draft":
        report["notes"].append(
            "Exactly one playbook draft was found. Reconcile into that directory unless the user "
            "overrides output_dir."
        )
    if not framework_names and args.test_framework.lower() == "auto":
        report["notes"].append(
            "No known test framework detected. Inspect project test commands and CI before choosing evidence."
        )
    if workspace_expansions:
        member_ids = [
            member_id
            for expansion in workspace_expansions
            for member_id in expansion.get("member_source_ids", [])
        ]
        report["notes"].append(
            "Workspace folder expanded into separate scan roots for each nested repo, "
            f"submodule, or product subfolder ({', '.join(member_ids)}). "
            "A source path is not assumed to be one repository."
        )
    if report["evidence_summary"]["linked_repository_candidates"]:
        report["notes"].append(
            "Additional nested Git repositories remain inside a scanned root. Confirm whether "
            "they should be separate sources before writing."
        )
    if report["evidence_summary"]["scope_warnings"]:
        report["notes"].append(
            "Repository instructions describe at least one source as a mock, fixture, generated copy, "
            "or unavailable implementation. Read those warnings and confirm the intended product scope."
        )
    if report["evidence_summary"]["viewport_fork_candidates"]:
        report["notes"].append(
            "Some screens may look different on phone and desktop. Only mark those journeys "
            "for dual-width checks."
        )
    if report["evidence_summary"]["auth_role_candidates"]:
        report["notes"].append(
            "Possible product roles or account types were found. Show them in Intake as "
            "assumptions to approve or correct. Do not invent tester accounts."
        )
    if report["evidence_summary"]["auth_gate_candidates"]:
        report["notes"].append(
            "Permission checks were found. Ask which roles should be able to pass them."
        )
    if prior_work_candidates and not drafts:
        report["notes"].append(
            "Prior QA, scenario, report, state, or API-client artifacts were found without a canonical "
            "playbook. Ask whether they are authoritative continuation evidence before creating a new path."
        )

    output = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        Path(args.output).expanduser().write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
