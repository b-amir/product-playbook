# Optional PDF or HTML export

Markdown is the default and only automatic output. Produce a single combined PDF or a single
HTML file only when the user explicitly asks. Never export during a normal create, edit,
reconciliation, or audit.

## Commands

```bash
python3 <skill-dir>/scripts/validate_playbook.py "<output_dir>"

# PDF (default): writes <output_dir>/playbook.pdf and removes intermediate HTML.
python3 <skill-dir>/scripts/export_playbook.py "<output_dir>" [--output PATH] [--force]

# HTML only: writes <output_dir>/playbook.html and leaves it in place.
python3 <skill-dir>/scripts/export_playbook.py "<output_dir>" --format html [--output PATH] [--force]
```

`export_playbook.py` reads only `README.md`, numbered chapters, and `results-template.md`.
It ignores `.product-playbook-state.json` and any non-Markdown file.

## Converter behavior

`--format pdf` builds print-ready HTML privately, then prints with the first working converter:

1. Google Chrome / Chromium / `google-chrome-stable` (headless; CI-safe flags as implemented)
2. `wkhtmltopdf`
3. `pandoc`

Require a real `%PDF` header before accepting output. On failure, report converter exit status
and stderr. Do not claim “no converter found” when converters were tried and failed.
Do not install a converter. Do not assume one is present.

`--format html` writes self-contained `playbook.html` and stops. Do not print it to PDF in
that mode.

## Derived artifacts

Treat `playbook.pdf` and `playbook.html` as regenerable. They are not part of the canonical
folder shape, are never written by the default workflow, and need not be reconciled on later
edits. Delete or regenerate them when Markdown changes.

Visual rules for the export surface live in `DESIGN.md` at the skill root.
