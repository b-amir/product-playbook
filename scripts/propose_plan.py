#!/usr/bin/env python3
"""Validate a plan JSON and write it for human review without rendering Markdown."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from schema_utils import validate_plan_file


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Propose-only gate: validate an evidence-backed plan and copy it to an "
            "output path without writing playbook Markdown or state."
        )
    )
    parser.add_argument("plan", help="Evidence-backed JSON plan")
    parser.add_argument(
        "output",
        help="Where to write the validated plan copy (for review)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite the output path if it exists.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    plan_path = Path(args.plan).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()
    try:
        plan = validate_plan_file(plan_path)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    if output_path.exists() and not args.force:
        raise SystemExit(f"output exists; pass --force to overwrite: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if plan_path != output_path:
        shutil.copyfile(plan_path, output_path)
    else:
        output_path.write_text(
            json.dumps(plan, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(
        json.dumps(
            {
                "propose_only": True,
                "plan": str(plan_path),
                "output": str(output_path),
                "chapters": len(plan.get("chapters", [])),
                "next": "Wait for user approval before render_playbook.py or patching Markdown",
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
