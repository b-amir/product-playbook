#!/usr/bin/env python3
"""Acquire evidence sources and produce a ready-to-execute playbook plan."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bootstrap product-playbook discovery from local paths or repository URLs."
    )
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        metavar="SOURCE_ID=PATH_OR_URL",
        help="Code evidence source. Repeat for multiple sources. At least one source of any kind is required.",
    )
    parser.add_argument(
        "--docs-source",
        action="append",
        default=[],
        metavar="SOURCE_ID=PATH_OR_URL",
        help="Documentation evidence source. Repeat for multiple sources.",
    )
    parser.add_argument(
        "--source-ref",
        action="append",
        default=[],
        metavar="SOURCE_ID=REF",
    )
    parser.add_argument("--draft-path")
    parser.add_argument("--output-dir")
    parser.add_argument("--workspace-dir")
    parser.add_argument(
        "--product-surface",
        choices=("auto", "frontend", "api", "fullstack", "cli", "service", "mobile"),
        default="auto",
    )
    parser.add_argument("--test-framework", default="auto")
    parser.add_argument("--max-items", type=int, default=500)
    parser.add_argument("--output", help="Write the bootstrap JSON report to this file")
    return parser.parse_args()


def add_repeated(command: list[str], flag: str, values: list[str]) -> None:
    for value in values:
        command.extend([flag, value])


def build_plan(discovery: dict[str, Any]) -> dict[str, Any]:
    accessible_sources = [source["source_id"] for source in discovery["sources"]]
    components = discovery.get("components", [])
    if discovery["ask_before_write"]:
        next_action = "ask_for_output_or_authoritative_draft"
    elif discovery["mode_suggestion"] == "reconcile":
        next_action = "inventory_then_reconcile"
    else:
        next_action = "analyze_then_create"
    return {
        **discovery,
        "bootstrap": {
            "ready": not discovery["ask_before_write"],
            "run_scope": "auto",
            "scope_decision": (
                "Use full only when accessible sources cover every intended product component. "
                "Otherwise use contribution and preserve inaccessible scenarios."
            ),
            "accessible_sources": accessible_sources,
            "component_count": len(components),
            "next_action": next_action,
            "read_first": sorted(
                {
                    instruction
                    for repository in discovery["repositories"]
                    for instruction in repository["instruction_files"]
                }
            ),
            "inspect_next": sorted(
                {
                    path
                    for repository in discovery["repositories"]
                    for path in [
                        *repository["ci_files"],
                        *repository["project_manifests"],
                    ]
                }
            ),
        },
    }


def main() -> int:
    args = parse_args()
    discover = Path(__file__).with_name("discover_product.py")
    command = [
        sys.executable,
        str(discover),
        "--product-surface",
        args.product_surface,
        "--test-framework",
        args.test_framework,
        "--max-items",
        str(args.max_items),
    ]
    add_repeated(command, "--source", args.source)
    add_repeated(command, "--docs-source", args.docs_source)
    add_repeated(command, "--source-ref", args.source_ref)
    for flag, value in (
        ("--draft-path", args.draft_path),
        ("--output-dir", args.output_dir),
        ("--workspace-dir", args.workspace_dir),
    ):
        if value:
            command.extend([flag, value])
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr or result.stdout, file=sys.stderr, end="")
        return result.returncode
    report = build_plan(json.loads(result.stdout))
    output = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        Path(args.output).expanduser().write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
