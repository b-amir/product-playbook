#!/usr/bin/env python3
"""Acquire evidence sources and produce a ready-to-execute playbook plan."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
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


def _display_path(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "?"
    if re.match(r"^(https?://|git@)", text):
        return text
    path = Path(text)
    parts = path.parts
    if len(parts) <= 4:
        return text
    return str(Path(*parts[-3:]))


def _caution_label(item: dict[str, Any]) -> str:
    kind = str(item.get("kind") or "")
    path = _display_path(item.get("path"))
    labels = {
        "declared-mock-or-fixture": f"mock/fixture note in {path}",
        "declared-source-unavailable": f"source-unavailable note in {path}",
        "declared-generated-copy": f"generated-copy note in {path}",
    }
    return labels.get(kind, f"scope note in {path}")


def _linked_label(item: dict[str, Any]) -> str:
    path = item.get("path") or item.get("git_root") or item.get("name") or "?"
    roles = item.get("assumed_roles") or []
    role_text = _role_label([str(role) for role in roles]) if roles else "related"
    display = _display_path(path)
    # Prefer the leaf folder name when the shortened path is still long.
    leaf = Path(str(path)).name or display
    if leaf and leaf not in display and len(display) > 48:
        display = leaf
    return f"{display} — {role_text}"


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
                "path_or_remote": _display_path(
                    source.get("supplied_remote")
                    or source.get("local_root")
                    or source.get("root")
                    or source.get("path")
                ),
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
                    "labels": [
                        str(label).strip()
                        for label in (item.get("labels") or [])
                        if str(label).strip()
                    ],
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
    linked_items: list[dict[str, Any]] = []
    for repository in discovery.get("repositories", []):
        for item in _sample(repository.get("linked_repository_candidates", []), 5):
            if isinstance(item, dict):
                linked_items.append(item)
    caution_items: list[dict[str, Any]] = []
    for repository in discovery.get("repositories", []):
        for item in _sample(repository.get("scope_warnings", []), 5):
            if isinstance(item, dict):
                caution_items.append(item)

    return {
        "headline": "What I found",
        "agreement_copy": "Correct me if I'm wrong.",
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
        "related_folders": linked_items,
        "cautions": caution_items,
        "scope": {
            "sources": [
                {
                    "name": folder["name"],
                    "path": folder["path_or_remote"],
                }
                for folder in folders
            ],
            "output_decision": discovery.get("output_decision"),
            "mode_suggestion": discovery.get("mode_suggestion"),
        },
    }


def _choice(key: str, label: str, *, recommended: bool = False, needs_text: bool = False) -> dict[str, Any]:
    item: dict[str, Any] = {"key": key, "label": label}
    if recommended:
        item["recommended"] = True
    if needs_text:
        item["needs_text"] = True
    return item


def build_findings_copy(assumptions: dict[str, Any]) -> dict[str, str]:
    folders = assumptions.get("folders_and_repos") or []
    folder_cell = (
        "; ".join(
            f"{folder['name']} → {folder.get('path_or_remote') or '?'} ({folder['what_it_is']})"
            for folder in folders
        )
        if folders
        else "none"
    )
    scope = assumptions.get("scope") or {}
    scope_sources = scope.get("sources") or []
    scope_cell = (
        "; ".join(
            f"{item.get('name')}={item.get('path')}"
            for item in scope_sources
            if item.get("name")
        )
        or "unknown"
    )
    drafts = assumptions.get("existing_playbook") or []
    if drafts:
        playbook = _display_path(
            drafts[0].get("path")
            or drafts[0].get("draft_path")
            or drafts[0].get("output_dir")
            or drafts[0]
        )
    else:
        playbook = "none"
    save_location = _display_path(
        assumptions.get("suggested_save_location") or "undecided"
    )
    roles = assumptions.get("product_roles") or []
    role_labels: list[str] = []
    seen_labels: set[str] = set()
    for item in roles:
        for label in item.get("labels") or []:
            raw = str(label).strip()
            if not raw:
                continue
            slug = re.sub(r"[_-]+", " ", raw).strip().lower()
            if not slug or slug in seen_labels:
                continue
            seen_labels.add(slug)
            role_labels.append(raw)
    # Collapse Admin/Administrator duplicates toward the longer form.
    lowered = {label.lower(): label for label in role_labels}
    if "admin" in lowered and "administrator" in lowered:
        role_labels = [
            label
            for label in role_labels
            if label.lower() != "admin"
        ]
    if role_labels:
        if len(role_labels) <= 8:
            role_text = ", ".join(role_labels)
        else:
            shown = ", ".join(role_labels[:8])
            role_text = f"{shown} (+{len(role_labels) - 8} more)"
    elif roles:
        paths = []
        seen_paths: set[str] = set()
        for item in roles:
            path = _display_path(item.get("where"))
            if not path or path in seen_paths:
                continue
            seen_paths.add(path)
            paths.append(path)
        if len(paths) <= 5:
            role_text = ", ".join(paths)
        else:
            role_text = f"{', '.join(paths[:5])} (+{len(paths) - 5} more files)"
    else:
        role_text = "none found"
    width = assumptions.get("screens_that_change_by_width") or []
    width_text = (
        ", ".join(_display_path(item.get("where")) for item in width[:3])
        if width
        else "none found"
    )
    gates = assumptions.get("permission_checks") or []
    gate_text = (
        ", ".join(_display_path(item.get("where")) for item in gates[:3])
        if gates
        else "none found"
    )
    related = assumptions.get("related_folders") or []
    related_text = (
        "; ".join(_linked_label(item) for item in related[:5]) if related else ""
    )
    if related and len(related) > 5:
        related_text = f"{related_text}; +{len(related) - 5} more"
    cautions = assumptions.get("cautions") or []
    caution_text = (
        "; ".join(_caution_label(item) for item in cautions[:5]) if cautions else ""
    )
    if cautions and len(cautions) > 5:
        caution_text = f"{caution_text}; +{len(cautions) - 5} more"
    product = (assumptions.get("product") or {}).get("summary") or "unknown"
    agreement = assumptions.get("agreement_copy") or "Correct me if I'm wrong."

    rows = [
        ("Scope", scope_cell),
        ("Product", product),
        ("Folders", folder_cell),
        ("Existing playbook", playbook),
        ("Save location", save_location),
        ("Product roles", role_text),
        ("Width-sensitive screens", width_text),
        ("Permission checks", gate_text),
    ]
    # Omit empty related/caution rows — count-only jargon ("2 linked") is worse than silence.
    if related_text:
        rows.append(("Nearby repos (not in Folders yet)", related_text))
    if caution_text:
        rows.append(("Mocks / fixtures / generated", caution_text))

    chat_block = "\n".join(
        [
            "## What I found",
            "",
            "| Item | Value |",
            "| --- | --- |",
            *[f"| {label} | {value} |" for label, value in rows],
            "",
            agreement,
        ]
    )
    return {
        "chat_block": chat_block,
        "disclaimer": agreement,
    }


def intake_fingerprint(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:12]


def build_intake(
    discovery: dict[str, Any],
    *,
    intent: str,
    defaulted_source_to_cwd: bool,
) -> dict[str, Any]:
    assumptions = build_working_assumptions(discovery)
    findings_copy = build_findings_copy(assumptions)
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
                f"Use the suggested path: {_display_path(suggested)}"
                if suggested
                else "Use the suggested path",
            )
        )
        save_choices.append(_choice("C", "Somewhere else", needs_text=True))
    else:
        save_choices.append(
            _choice(
                "A",
                f"Use the suggested path: {_display_path(suggested)}"
                if suggested
                else "Use the suggested path",
                recommended=True,
            )
        )
        save_choices.append(_choice("B", "Somewhere else", needs_text=True))

    questions: list[dict[str, Any]] = [
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
        action_recommended,
        "A",
        save_recommended,
    ]

    if assumptions["related_folders"]:
        questions.append(
            {
                "id": "include_related_folders",
                "required": True,
                "prompt": "Include the nearby repos listed above?",
                "selection": "single",
                "choices": [
                    _choice("A", "Include none", recommended=True),
                    _choice("B", "Include some (name them after your letters)", needs_text=True),
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
                "prompt": "Include the mocks / fixtures / generated paths listed above?",
                "selection": "single",
                "choices": [
                    _choice("A", "Leave them out", recommended=True),
                    _choice(
                        "B",
                        "Include some anyway (name them after your letters)",
                        needs_text=True,
                    ),
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

    choice_lines = [
        "## Choose",
        "",
        "Reply with letters only.",
        f"Recommended: `{recommended_reply}`",
        "",
    ]
    for index, question in enumerate(questions, start=1):
        choice_lines.append(f"### {index}. {question['prompt']}")
        choice_lines.append("")
        for choice in question["choices"]:
            marker = " ← recommended" if choice.get("recommended") else ""
            choice_lines.append(f"- **{choice['key']}.** {choice['label']}{marker}")
        choice_lines.append("")
    choice_lines.extend(
        [
            "---",
            "",
            f"Reply like: `{recommended_reply}`",
            "",
            "Or just: `recommended`",
        ]
    )
    choices_block = "\n".join(choice_lines)
    intake_message = f"{findings_copy['chat_block']}\n\n{choices_block}\n"
    fingerprint_payload = {
        "working_assumptions": assumptions,
        "recommended_reply": recommended_reply,
        "question_ids": [question["id"] for question in questions],
    }
    fingerprint = intake_fingerprint(fingerprint_payload)

    return {
        "intent": intent,
        "defaulted_source_to_current_directory": defaulted_source_to_cwd,
        "requires_user_confirmation": intent == "auto",
        "working_assumptions": assumptions,
        "findings_chat_block": findings_copy["chat_block"],
        "intake_message": intake_message,
        "intake_fingerprint": fingerprint,
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
            "prefer_structured_polls": False,
            "intake_uses_polls": False,
            "intake_format": "single_chat_message",
            "polls_allowed_for": ["plan_gate", "after_plan"],
            "fallback": "lettered_menu",
            "accept_recommended_alias": True,
            "minimize_free_text": True,
            "free_text_only_when": "needs_text choice is selected or table corrections",
        },
        "presentation_notes": [
            "HARD RULE: Intake uses NO polls and NO AskQuestion widgets.",
            "HARD RULE: Run bootstrap_playbook.py, then print intake.intake_message VERBATIM.",
            "HARD RULE: Preserve every blank line and heading from intake_message. Do not collapse options onto one line.",
            "Do not paraphrase, trim, reorder, or invent table rows. Same sources → same message.",
            "If two chats disagree, compare Scope rows and --source arguments first.",
            "Polls are allowed later for plan_gate and after_plan only.",
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
