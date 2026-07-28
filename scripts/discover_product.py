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

from source_utils import (
    SourceSpec,
    acquire_source,
    create_workspace,
    ensure_unique_sources,
    is_remote_locator,
    legacy_specs,
    parse_source_spec,
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
    "generated",
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
DOC_SUFFIXES = {".adoc", ".md", ".mdx", ".rst", ".txt"}
CONTRACT_SUFFIXES = {".graphql", ".gql", ".proto", ".raml"}
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
    r"(route|router|routing|controller|endpoint|handler|urls|command|cli|worker|job|consumer)",
    re.IGNORECASE,
)
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
        choices=("auto", "frontend", "api", "fullstack", "cli", "service", "mobile"),
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


def detect_contracts(files: list[Path], root: Path) -> list[str]:
    contracts: list[str] = []
    for path in files:
        lower = path.name.lower()
        if (
            path.suffix.lower() in CONTRACT_SUFFIXES
            or lower.startswith("openapi.")
            or lower.startswith("swagger.")
            or "asyncapi" in lower
        ):
            contracts.append(relative(path, root))
    return sorted(contracts)


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


def detect_project_signals(project_text: str, files: list[Path]) -> list[dict[str, Any]]:
    signals: dict[str, list[str]] = {
        "api": [],
        "cli": [],
        "service": [],
        "mobile": [],
    }
    token_groups = {
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
        "mobile": ("react-native", "flutter", "androidx", "swiftui"),
    }
    for category, tokens in token_groups.items():
        for token in tokens:
            if token in project_text:
                add_signal(signals, category, f"{token} project dependency")
                break
    if any(path.name in {"AndroidManifest.xml", "pubspec.yaml"} for path in files):
        add_signal(signals, "mobile", "mobile project manifest")
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
    signal_names = {signal["name"] for signal in project_signals}
    browser = bool(classified["browser_test_files"])
    api = bool(classified["api_test_files"] or contracts or "api" in signal_names)
    cli = bool(classified["cli_test_files"] or "cli" in signal_names)
    service = bool(classified["service_test_files"] or "service" in signal_names)
    mobile = bool(classified["mobile_test_files"] or "mobile" in signal_names)
    if browser and api:
        return "fullstack"
    if browser:
        return "frontend"
    if api:
        return "api"
    if cli:
        return "cli"
    if service:
        return "service"
    if mobile:
        return "mobile"
    return "unknown"


def surface_profile(
    classified: dict[str, list[str]],
    contracts: list[str],
    project_signals: list[dict[str, Any]],
) -> dict[str, Any]:
    signal_names = {signal["name"] for signal in project_signals}
    scores: dict[str, float] = {}
    if classified["browser_test_files"]:
        scores["frontend"] = 0.95
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
        contracts = detect_contracts(component_files, component_root)
        signals = detect_project_signals(project_text, component_files)
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
    contracts = detect_contracts(files, root)
    project_signals = detect_project_signals(project_text, files)
    surface = select_surface(args.product_surface, classified, contracts, project_signals)
    profile = surface_profile(classified, contracts, project_signals)
    if args.product_surface != "auto":
        profile = {
            "surfaces": [args.product_surface],
            "surface_confidence": {args.product_surface: 1.0},
            "primary_surface": args.product_surface,
        }
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
        "test_commands": detect_test_commands(root, files, frameworks),
        "unclassified_test_candidates": unclassified,
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
        docs = [
            relative(path, root if root.is_dir() else root.parent)
            for path in files
            if path.is_file() and path.suffix.lower() in DOC_SUFFIXES
        ]
        reports.append(
            {"source_id": source_id, "root": str(root), "files": sorted(docs)[:max_items]}
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
    if args.draft_path:
        explicit_draft = Path(args.draft_path).expanduser().resolve()
        explicit_directory = explicit_draft.parent if explicit_draft.is_file() else explicit_draft
        if str(explicit_directory) not in {item["path"] for item in drafts}:
            raise SystemExit(
                "explicit draft path is missing or does not contain recognizable playbook "
                f"Markdown: {explicit_draft}"
            )
    explicit_output = Path(args.output_dir).expanduser().resolve() if args.output_dir else None
    multi_evidence = len(code_roots) > 1 or len(docs_paths) > 0

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
    elif (
        len(code_sources) == 1
        and code_sources[0].locator_type == "local"
        and not docs_paths
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
        "repositories": repositories,
        "documentation": discover_docs(
            [(source.source_id, source.root) for source in docs_sources],
            args.max_items,
        ),
        "selected_frameworks": selected_frameworks or ["unknown"],
        "existing_playbook_candidates": drafts,
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

    output = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        Path(args.output).expanduser().write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
