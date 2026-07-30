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
            "Requested workflow. Auto discovers first, then asks the user to approve or correct "
            "what was found before any write."
        ),
    )
    parser.add_argument("--test-framework", default="auto")
    parser.add_argument("--max-items", type=int, default=500)
    parser.add_argument("--output", help="Write the bootstrap JSON report to this file")
    return parser.parse_args()


def add_repeated(command: list[str], flag: str, values: list[str]) -> None:
    for value in values:
        command.extend([flag, value])


def _sample(items: list[Any], limit: int = 8) -> list[Any]:
    return items[:limit]


def _role_label(roles: list[str]) -> str:
    if not roles:
        return "unknown"
    friendly = {
        "frontend": "web app",
        "api": "API",
        "fullstack": "full stack",
        "cli": "command line",
        "service": "service",
        "worker": "background jobs",
        "mobile": "mobile app",
        "rag": "search / RAG",
        "library": "library",
        "sdk": "SDK",
        "integration": "integration",
        "extension": "extension",
        "data": "data",
        "contracts": "contracts",
        "docs": "documentation",
        "documentation": "documentation",
        "tooling": "tooling",
    }
    return ", ".join(friendly.get(role, role) for role in roles)


def build_working_assumptions(discovery: dict[str, Any]) -> dict[str, Any]:
    repository_by_source = {
        repository["source_id"]: repository
        for repository in discovery.get("repositories", [])
    }
    folders: list[dict[str, Any]] = []
    for source in discovery.get("source_addresses", []):
        source_id = source["source_id"]
        if source["kind"] == "docs":
            roles = ["documentation"]
        else:
            repository = repository_by_source.get(source_id, {})
            roles = repository.get("surfaces", ["unknown"])
        folders.append(
            {
                "name": source_id,
                "kind": source["kind"],
                "what_it_is": _role_label(roles),
                "path_or_remote": source.get("supplied_remote")
                or source.get("local_root")
                or source.get("root")
                or source.get("path"),
            }
        )

    surfaces: list[str] = []
    for repository in discovery.get("repositories", []):
        for surface in repository.get("surfaces", []):
            if surface not in surfaces:
                surfaces.append(surface)

    product_roles: list[dict[str, str]] = []
    viewport_areas: list[dict[str, str]] = []
    permission_checks: list[dict[str, str]] = []
    for repository in discovery.get("repositories", []):
        for item in repository.get("auth_role_candidates", []):
            product_roles.append(
                {
                    "where": item.get("path", ""),
                    "why": item.get("reason", "role signal"),
                    "tester_path": "unknown",
                }
            )
        for item in repository.get("viewport_fork_candidates", []):
            viewport_areas.append(
                {
                    "where": item.get("path", ""),
                    "why": item.get("reason", "viewport signal"),
                }
            )
        for item in repository.get("auth_gate_candidates", []):
            permission_checks.append(
                {
                    "where": item.get("path", ""),
                    "why": item.get("reason", "permission signal"),
                }
            )

    drafts = [
        *discovery.get("existing_playbook_candidates", []),
        *discovery.get("linked_playbook_candidates", []),
    ]
    linked = [
        {
            "source_id": repository["source_id"],
            "items": _sample(repository.get("linked_repository_candidates", []), 5),
        }
        for repository in discovery.get("repositories", [])
        if repository.get("linked_repository_candidates")
    ]
    cautions = [
        {
            "source_id": repository["source_id"],
            "items": _sample(repository.get("scope_warnings", []), 5),
        }
        for repository in discovery.get("repositories", [])
        if repository.get("scope_warnings")
    ]

    return {
        "headline": "What I found",
        "agreement_copy": (
            "These are working assumptions from the repo, not the final playbook. "
            "Pick Yes below to continue with them, or pick No and add short corrections."
        ),
        "product": {
            "looks_like": surfaces or ["unknown"],
            "summary": _role_label(surfaces) if surfaces else "unknown",
        },
        "folders_and_repos": folders,
        "existing_playbook": _sample(drafts, 5),
        "suggested_save_location": discovery.get("recommended_output_dir"),
        "product_roles": _sample(product_roles, 8),
        "screens_that_change_by_width": _sample(viewport_areas, 8),
        "permission_checks": _sample(permission_checks, 8),
        "related_folders": linked,
        "cautions": cautions,
    }


def _choice(key: str, label: str, *, recommended: bool = False, needs_text: bool = False) -> dict[str, Any]:
    item: dict[str, Any] = {"key": key, "label": label}
    if recommended:
        item["recommended"] = True
    if needs_text:
        item["needs_text"] = True
    return item


def build_intake(
    discovery: dict[str, Any],
    *,
    intent: str,
    defaulted_source_to_cwd: bool,
) -> dict[str, Any]:
    assumptions = build_working_assumptions(discovery)
    has_playbook = bool(assumptions["existing_playbook"])
    suggested = assumptions.get("suggested_save_location")
    action_recommended = "A" if has_playbook else "B"
    save_recommended = "A"

    folder_choices = [
        _choice("A", "All folders listed above", recommended=True),
    ]
    # Reserve B..Y for individual folders when the user wants a subset.
    next_key = ord("B")
    for folder in assumptions["folders_and_repos"]:
        if next_key >= ord("Z"):
            break
        folder_choices.append(
            _choice(
                chr(next_key),
                f"Only {folder['name']} ({folder['what_it_is']})",
            )
        )
        next_key += 1
    folder_choices.append(
        _choice("Z", "Add another folder or Git URL", needs_text=True)
    )

    save_choices: list[dict[str, Any]] = []
    if has_playbook:
        save_choices.append(
            _choice("A", "Use the existing playbook path", recommended=True)
        )
        save_choices.append(
            _choice(
                "B",
                f"Use the suggested path: {suggested}"
                if suggested
                else "Use the suggested path",
            )
        )
        save_choices.append(_choice("C", "Somewhere else", needs_text=True))
    else:
        save_choices.append(
            _choice(
                "A",
                f"Use the suggested path: {suggested}"
                if suggested
                else "Use the suggested path",
                recommended=True,
            )
        )
        save_choices.append(_choice("B", "Somewhere else", needs_text=True))

    questions: list[dict[str, Any]] = [
        {
            "id": "approve_or_correct_findings",
            "required": True,
            "prompt": "Does this look right?",
            "selection": "single",
            "choices": [
                _choice("A", "Yes, continue with these findings", recommended=True),
                _choice("B", "No, I will correct them in this reply", needs_text=True),
            ],
            "recommended": "A",
        },
        {
            "id": "choose_action",
            "required": True,
            "prompt": "What should I do?",
            "selection": "single",
            "choices": [
                _choice(
                    "A",
                    "Update the existing playbook",
                    recommended=has_playbook,
                ),
                _choice(
                    "B",
                    "Create a new playbook",
                    recommended=not has_playbook,
                ),
                _choice("C", "Review only (no file changes)"),
                _choice("D", "Run checks against the live product"),
            ],
            "recommended": action_recommended,
        },
        {
            "id": "choose_folders",
            "required": True,
            "prompt": "Which folders should I use?",
            "selection": "single_or_multi",
            "choices": folder_choices,
            "recommended": "A",
        },
        {
            "id": "choose_save_location",
            "required": True,
            "prompt": "Where should the playbook live?",
            "selection": "single",
            "choices": save_choices,
            "recommended": save_recommended,
        },
    ]

    recommended_letters = [
        "A",
        action_recommended,
        "A",
        save_recommended,
    ]

    if assumptions["related_folders"]:
        questions.append(
            {
                "id": "include_related_folders",
                "required": True,
                "prompt": "Include related folders?",
                "selection": "single",
                "choices": [
                    _choice("A", "Include none", recommended=True),
                    _choice("B", "Include some", needs_text=True),
                ],
                "recommended": "A",
            }
        )
        recommended_letters.append("A")
    if assumptions["cautions"]:
        questions.append(
            {
                "id": "handle_cautions",
                "required": True,
                "prompt": "Mocks, fixtures, or generated copies?",
                "selection": "single",
                "choices": [
                    _choice("A", "Leave them out", recommended=True),
                    _choice("B", "Include some anyway", needs_text=True),
                ],
                "recommended": "A",
            }
        )
        recommended_letters.append("A")

    recommended_reply = " ".join(recommended_letters)

    # Keep legacy assumption keys for older agents while preferring working_assumptions.
    role_assumptions = [
        {
            "source_id": folder["name"],
            "kind": folder["kind"],
            "assumed_roles": [folder["what_it_is"]],
        }
        for folder in assumptions["folders_and_repos"]
    ]

    return {
        "intent": intent,
        "defaulted_source_to_current_directory": defaulted_source_to_cwd,
        "requires_user_confirmation": intent == "auto",
        "working_assumptions": assumptions,
        "source_role_assumptions": role_assumptions,
        "canonical_output_assumption": {
            "decision": discovery.get("output_decision"),
            "path": discovery.get("recommended_output_dir"),
        },
        "continuation_assumption": discovery.get("continuation_suggestion"),
        "evidence_summary": discovery.get("evidence_summary", {}),
        "questions": questions,
        "recommended_reply": recommended_reply,
        "reply_hint": (
            f"Reply with option letters only, like: {recommended_reply}\n"
            "Or reply: recommended"
        ),
        "ux": {
            "prefer_structured_polls": True,
            "fallback": "lettered_menu",
            "accept_recommended_alias": True,
            "minimize_free_text": True,
            "free_text_only_when": "needs_text choice is selected",
        },
        "presentation_notes": [
            "Show What I found first.",
            "Prefer harness polls or multi-select when available. Pre-select recommended answers.",
            "If no poll UI exists, show one lettered menu and ask for letters only.",
            f"Show Recommended: {recommended_reply}",
            "Accept the bare word recommended as the full recommended reply.",
            "Do not ask the user to write sentences when a letter will do.",
            "Never ask the user about digests, fingerprints, hashes, or session IDs.",
        ],
        "plan_gate_choices": [
            _choice("A", "Approve the plan", recommended=True),
            _choice("B", "Adjust the plan", needs_text=True),
            _choice("C", "Review only (do not write files)"),
        ],
        "after_plan_choices": [
            _choice("A", "Stop here", recommended=True),
            _choice("B", "Quick smoke check while writing"),
            _choice("C", "Full product check → findings folder"),
            _choice("D", "Export PDF"),
            _choice("E", "Export HTML"),
        ],
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
