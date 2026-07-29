---
name: product-playbook-export
description: >-
  Export an existing validated product playbook to a single PDF or HTML file.
  Use only when the user explicitly asks for playbook.pdf or playbook.html.
  Never invent playbook content; never run during normal create or reconcile.
---

# Product Playbook Export

Thin companion. Markdown remains canonical.

1. Confirm the playbook directory.
2. Validate Markdown.
3. Export PDF (default) or HTML per user ask.

```bash
python3 <skill-dir>/../../scripts/validate_playbook.py "<output_dir>"
python3 <skill-dir>/../../scripts/export_playbook.py "<output_dir>" [--format html]
```

Details: [../../references/export.md](../../references/export.md).
