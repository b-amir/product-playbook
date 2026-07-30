---
name: product-playbook-audit
description: >-
  Audit an existing product playbook against current evidence without editing
  Markdown or state. Use when the user asks for a playbook audit, drift check,
  coverage gap review, or read-only reconciliation report. Prefer the main
  product-playbook skill for create or edit runs.
---

# Product Playbook Audit

Read-only companion to `product-playbook`. Same discovery and evidence rules.
Never write playbook Markdown, state, PDF/HTML, or findings unless the user
explicitly switches mode.

## Steps

1. Run bootstrap / inventory with `--check-state` (add `--drift` for CI exit codes).
2. Print **What I found** in chat first, then a short What changed summary, then polls.
   Never ask “look right?” before findings are visible.
3. Report Keep / Update / Add / Remove / Needs evidence — do not patch.
4. Emit End Report with `Mode: audit`.

Skill root scripts live two levels up: `../../scripts/`.

```bash
python3 <skill-dir>/../../scripts/inventory_playbook.py "<output_dir>" \
  --source "SOURCE_ID=<root>" \
  --check-state --drift
```

Full protocol: [../../references/run-protocol.md](../../references/run-protocol.md).
