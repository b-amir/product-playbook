#!/usr/bin/env python3
"""Acquire evidence sources and produce a ready-to-execute playbook plan."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


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
        choices=SURFACE_CHOICES,
        default="auto",
    )
    parser.add_argument(
        "--intent",
        choices=("auto", "inspect", "audit", "create", "reconcile", "contribute"),
        default="auto",
        help=(
            "Requested workflow. Auto performs first-run discovery and asks the user to confirm "
            "sources, roles, prior work, and the next action before any write."
        ),
    )
    parser.add_argument("--test-framework", default="auto")
    parser.add_argument("--max-items", type=int, default=500)
    parser.add_argument("--output", help="Write the bootstrap JSON report to this file")
    return parser.parse_args()


def add_repeated(command: list[str], flag: str, values: list[str]) -> None:
    for value in values:
        command.extend([flag, value])


def build_intake(
    discovery: dict[str, Any],
    *,
    intent: str,
    defaulted_source_to_cwd: bool,
) -> dict[str, Any]:
    repository_by_source = {
        repository["source_id"]: repository
        for repository in discovery.get("repositories", [])
    }
    role_assumptions = []
    for source in discovery.get("source_addresses", []):
        source_id = source["source_id"]
        if source["kind"] == "docs":
            roles = ["documentation"]
        else:
            repository = repository_by_source.get(source_id, {})
            roles = repository.get("surfaces", ["unknown"])
        role_assumptions.append(
            {
                "source_id": source_id,
                "kind": source["kind"],
                "assumed_roles": roles,
            }
        )

    questions: list[dict[str, Any]] = [
        {
            "id": "confirm_source_addresses",
            "required": True,
            "prompt": (
                "Are these the correct local and remote addresses for the repositories currently "
                "in scope?"
            ),
            "sources": discovery.get("source_addresses", []),
        },
        {
            "id": "confirm_source_roles",
            "required": True,
            "prompt": (
                "Are these repository roles correct, including product, documentation, API, RAG, "
                "worker, integration, SDK, helper-library, contract, and tooling roles?"
            ),
            "assumptions": role_assumptions,
        },
    ]
    drafts = discovery.get("existing_playbook_candidates", [])
    linked_drafts = discovery.get("linked_playbook_candidates", [])
    prior_work = discovery.get("prior_work_candidates", [])
    if drafts or linked_drafts or prior_work:
        questions.append(
            {
                "id": "continue_previous_work",
                "required": True,
                "prompt": (
                    "I found evidence of previous playbook, QA, scenario, report, or state work. "
                    "Should I continue the existing canonical path and add to it?"
                ),
                "continuation_suggestion": discovery.get("continuation_suggestion"),
                "playbook_candidates": [*drafts, *linked_drafts],
                "prior_work_sample": prior_work[:25],
            }
        )
    if discovery.get("evidence_summary", {}).get("linked_repository_candidates"):
        questions.append(
            {
                "id": "include_linked_repositories",
                "required": True,
                "prompt": (
                    "I found linked or nested repositories. Which should be added as independent "
                    "evidence sources with stable source IDs?"
                ),
                "candidates": [
                    {
                        "source_id": repository["source_id"],
                        "repositories": repository.get(
                            "linked_repository_candidates", []
                        ),
                    }
                    for repository in discovery.get("repositories", [])
                    if repository.get("linked_repository_candidates")
                ],
            }
        )
    if discovery.get("evidence_summary", {}).get("scope_warnings"):
        questions.append(
            {
                "id": "confirm_product_scope",
                "required": True,
                "prompt": (
                    "Repository instructions describe mock, fixture, generated, or unavailable "
                    "source. What is the intended real product scope?"
                ),
                "warnings": [
                    {
                        "source_id": repository["source_id"],
                        "items": repository.get("scope_warnings", []),
                    }
                    for repository in discovery.get("repositories", [])
                    if repository.get("scope_warnings")
                ],
            }
        )
    if intent == "auto":
        questions.append(
            {
                "id": "choose_action",
                "required": True,
                "prompt": (
                    "Do you want an audit only, a focused edit or reconciliation, a new playbook, "
                    "or verification through tests and supported interfaces?"
                ),
            }
        )

    return {
        "intent": intent,
        "defaulted_source_to_current_directory": defaulted_source_to_cwd,
        "requires_user_confirmation": intent == "auto",
        "source_role_assumptions": role_assumptions,
        "canonical_output_assumption": {
            "decision": discovery.get("output_decision"),
            "path": discovery.get("recommended_output_dir"),
        },
        "continuation_assumption": discovery.get("continuation_suggestion"),
        "evidence_summary": discovery.get("evidence_summary", {}),
        "questions": questions,
    }


def build_plan(
    discovery: dict[str, Any],
    *,
    intent: str,
    defaulted_source_to_cwd: bool,
) -> dict[str, Any]:
    accessible_sources = [source["source_id"] for source in discovery["sources"]]
    components = discovery.get("components", [])
    intake = build_intake(
        discovery,
        intent=intent,
        defaulted_source_to_cwd=defaulted_source_to_cwd,
    )
    if intake["requires_user_confirmation"]:
        next_action = "present_findings_and_confirm"
    elif discovery["ask_before_write"]:
        next_action = "ask_for_output_or_authoritative_draft"
    elif discovery["mode_suggestion"] == "reconcile":
        next_action = "inventory_then_reconcile"
    else:
        next_action = "analyze_then_create"
    return {
        **discovery,
        "intake": intake,
        "bootstrap": {
            "ready": (
                not discovery["ask_before_write"]
                and not intake["requires_user_confirmation"]
            ),
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
                        *repository["contract_candidates"],
                        *[
                            item["path"]
                            for item in repository.get(
                                "documentation_candidates", []
                            )
                        ],
                    ]
                }
            ),
        },
    }


def main() -> int:
    args = parse_args()
    defaulted_source_to_cwd = not args.source and not args.docs_source
    if defaulted_source_to_cwd:
        args.source = [f"product={Path.cwd()}"]
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
    report = build_plan(
        json.loads(result.stdout),
        intent=args.intent,
        defaulted_source_to_cwd=defaulted_source_to_cwd,
    )
    output = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        Path(args.output).expanduser().write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
