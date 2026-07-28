#!/usr/bin/env python3
"""Export a validated playbook to a single PDF or HTML file.

Markdown remains the source of truth and the default output. This exporter is
opt-in only and produces a derived, non-canonical artifact. Run
``validate_playbook.py`` before exporting so the export never ships an invalid book.

Output modes:

- ``--format pdf`` (default): build a print-ready HTML in a private location, then
  print it to ``<output_dir>/playbook.pdf`` using the first available converter
  (Google Chrome / Chromium headless, wkhtmltopdf, or pandoc). The intermediate
  HTML is deleted afterwards. If no converter is found, the export fails with a
  clear message instead of leaving an HTML file behind.
- ``--format html``: write a single self-contained ``<output_dir>/playbook.html``
  and leave it in place. No PDF is produced and nothing is deleted.

Standard library only, Python 3.9+.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Iterable, Optional


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Export a playbook directory to a single PDF or HTML file. "
            "Markdown stays the default; this is an opt-in export."
        )
    )
    parser.add_argument("output_dir", help="Validated playbook directory")
    parser.add_argument(
        "--format",
        choices=("pdf", "html"),
        default="pdf",
        help="Output format. 'pdf' (default) prints to PDF and removes the "
        "intermediate HTML. 'html' keeps a standalone HTML and skips the PDF.",
    )
    parser.add_argument(
        "--output",
        help=(
            "Destination path. Defaults to <output_dir>/playbook.pdf for --format pdf "
            "and <output_dir>/playbook.html for --format html."
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing output file.",
    )
    return parser.parse_args()


# --------------------------------------------------------------------------- #
# Playbook file collection
# --------------------------------------------------------------------------- #

def collect_files(output_dir: Path) -> list[Path]:
    """Return playbook Markdown files in tester-facing order."""
    if not output_dir.is_dir():
        raise ValueError(f"not a directory: {output_dir}")
    readme = output_dir / "README.md"
    results = output_dir / "results-template.md"
    missing = [
        name
        for name, path in (("README.md", readme), ("results-template.md", results))
        if not path.is_file()
    ]
    if missing:
        raise ValueError("missing required file(s): " + ", ".join(missing))
    chapters = sorted(
        path for path in output_dir.glob("[0-9][0-9]-*.md") if path.is_file()
    )
    if not chapters:
        raise ValueError("no numbered chapter files (NN-*.md) found")
    return [readme, *chapters, results]


# --------------------------------------------------------------------------- #
# Minimal Markdown renderer for the subset this skill emits.
# A scenario ("## ID: Title") is wrapped so its body can be indented as a unit.
# --------------------------------------------------------------------------- #

_FENCE = re.compile(r"^(\s*)(```+|~~~+)(.*)$")
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_BULLET = re.compile(r"^(\s*)[-*+]\s+(.+)$")
_ORDERED = re.compile(r"^(\s*)(\d+)\.\s+(.+)$")
_TABLE_ROW = re.compile(r"^\|.*\|\s*$")
_TABLE_SEP = re.compile(r"^\|?\s*:?-{2,}.*$")
_SCENARIO_HEADING = re.compile(r"^([A-Z][A-Z0-9]{1,5}-\d{2,3})\s*:")


def slugify(text: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return cleaned or "section"


def _file_anchor(path: Path) -> str:
    return slugify(path.stem)


def _escape(text: str) -> str:
    return html.escape(text, quote=False)


_CODE_SPAN = re.compile(r"`([^`]+)`")
_BOLD = re.compile(r"\*\*([^*]+?)\*\*")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_TASK_PREFIX = re.compile(r"^\[\s?[xX ]\s?\]\s*")
_SCENARIO_ID_LINE = re.compile(
    r"^(?:\[\s?[xX ]\s?\]\s*)?([A-Z][A-Z0-9]{1,5}-\d{2,3}\b.*)$"
)

_FIELD_ONLY = re.compile(r"^\*\*([^*]+)\*\*$")
_FIELD_KEYS = {
    "goal": "goal",
    "who": "who",
    "steps": "steps",
    "expected": "expected",
    "setup": "setup",
    "cleanup": "cleanup",
    "note": "note",
    "notes": "note",
    "record": "record",
    "optional": "optional",
    "optional follow-up": "optional",
    "handoff": "handoff",
}
_FIELD_LABELS = {
    "goal": "Goal",
    "who": "Who",
    "steps": "Steps",
    "expected": "Expected",
    "setup": "Setup",
    "cleanup": "Cleanup",
    "note": "Note",
    "record": "Record",
    "optional": "Optional follow-up",
    "handoff": "Handoff",
}


def _render_inline(text: str) -> str:
    """Render inline Markdown without corrupting generated tags.

    Earlier versions inserted raw ``<a>`` / ``<strong>`` then escaped the whole
    string and only partially un-escaped, leaving ``&gt;`` in opening tags so
    link labels vanished in tables and maps.
    """
    placeholders: list[str] = []

    def stash(fragment: str) -> str:
        placeholders.append(fragment)
        return f"\x00{len(placeholders) - 1}\x00"

    def restore(value: str) -> str:
        return re.sub(
            r"\x00(\d+)\x00",
            lambda match: placeholders[int(match.group(1))],
            value,
        )

    work = _CODE_SPAN.sub(
        lambda match: stash(f"<code>{_escape(match.group(1))}</code>"),
        text,
    )

    def render_link(match: "re.Match[str]") -> str:
        label_raw = match.group(1)
        target = match.group(2).strip()
        label_work = _BOLD.sub(
            lambda bold: stash(f"<strong>{_escape(bold.group(1))}</strong>"),
            label_raw,
        )
        label_html = restore(_escape(label_work))
        if target.endswith(".md") and "/" not in target and "#" not in target:
            href = f"#{slugify(Path(target).stem)}"
            return stash(f'<a href="{html.escape(href, quote=True)}">{label_html}</a>')
        safe_target = html.escape(target, quote=True)
        return stash(f'<a href="{safe_target}">{label_html}</a>')

    work = _LINK.sub(render_link, work)
    work = _BOLD.sub(
        lambda match: stash(f"<strong>{_escape(match.group(1))}</strong>"),
        work,
    )
    return restore(_escape(work))


def _table_cell(cell: str, *, header: bool = False) -> str:
    tag = "th" if header else "td"
    if not cell.strip():
        # Empty result / coverage cells are write-in fields, not blank holes.
        return f'<{tag} class="write-cell"><span class="write-line"></span></{tag}>'
    return f"<{tag}>{_render_inline(cell)}</{tag}>"


def _render_table(rows: list[str]) -> str:
    cells = [
        [cell.strip() for cell in row.strip().strip("|").split("|")]
        for row in rows
    ]
    if len(cells) < 2:
        return "".join(f"<p>{_render_inline(row)}</p>" for row in rows)
    header = cells[0]
    out = ["<table>", "<thead><tr>"]
    out.extend(_table_cell(cell, header=True) for cell in header)
    out.append("</tr></thead><tbody>")
    body_rows = cells[2:] if (len(cells) > 2 and _TABLE_SEP.match(cells[1][0])) else cells[1:]
    for row in body_rows:
        if all(re.fullmatch(r":?-{2,}:", cell or "-") for cell in row):
            continue
        out.append("<tr>")
        out.extend(_table_cell(cell) for cell in row)
        out.append("</tr>")
    out.append("</tbody></table>")
    return "".join(out)


def _checklist_item_label(line: str) -> Optional[str]:
    stripped = line.strip()
    if not stripped:
        return None
    match = _SCENARIO_ID_LINE.match(stripped)
    if match:
        return match.group(1).strip()
    if _TASK_PREFIX.match(stripped):
        return _TASK_PREFIX.sub("", stripped).strip() or None
    return None


def _looks_like_checklist(lines: list[str]) -> bool:
    nonempty = [line for line in lines if line.strip()]
    if not nonempty:
        return False
    matched = sum(1 for line in nonempty if _checklist_item_label(line))
    return matched == len(nonempty)


def _render_checklist(lines: list[str]) -> str:
    items: list[str] = []
    for line in lines:
        label = _checklist_item_label(line)
        if not label:
            continue
        items.append(
            "<li>"
            '<span class="tick" aria-hidden="true"></span>'
            f"<span class=\"label\">{_escape(label)}</span>"
            "</li>"
        )
    return '<ul class="checklist">\n' + "\n".join(items) + "\n</ul>"


def _render_write_in(rows: int = 4) -> str:
    rules = "".join('<div class="rule"></div>' for _ in range(max(rows, 2)))
    return f'<div class="write-in" role="presentation">{rules}</div>'


def _render_fence(info: str, code_lines: list[str]) -> str:
    """Promote playbook write-in / checklist fences; keep real code as code."""
    if not any(line.strip() for line in code_lines):
        return _render_write_in(4)
    if _looks_like_checklist(code_lines):
        return _render_checklist(code_lines)
    lang_class = f' class="language-{_escape(info)}"' if info else ""
    return (
        f"<pre><code{lang_class}>"
        f"{_escape(chr(10).join(code_lines))}"
        "</code></pre>"
    )


def render_markdown(body: str) -> str:
    lines = body.splitlines()
    out: list[str] = []
    i = 0
    paragraph: list[str] = []
    scenario_open = False
    # After a lone **Goal** / **Who** label, the next block is the value.
    pending_field: Optional[str] = None

    def flush_paragraph() -> None:
        nonlocal pending_field
        if not paragraph:
            return
        text = " ".join(paragraph).strip()
        paragraph.clear()
        field_match = _FIELD_ONLY.match(text)
        if field_match:
            key = _FIELD_KEYS.get(field_match.group(1).strip().lower())
            if key in ("goal", "who"):
                # Goal and Who become typed values, not shouted labels.
                pending_field = key
                return
            if key:
                pending_field = None
                out.append(f'<p class="field-label">{_FIELD_LABELS[key]}</p>')
                return
        css_class = ""
        if pending_field == "goal":
            css_class = ' class="scenario-goal"'
            pending_field = None
        elif pending_field == "who":
            css_class = ' class="scenario-who"'
            pending_field = None
        out.append(f"<p{css_class}>{_render_inline(text)}</p>")

    def close_scenario() -> None:
        nonlocal scenario_open, pending_field
        if scenario_open:
            out.append("</div></article>")
            scenario_open = False
        pending_field = None

    while i < len(lines):
        line = lines[i]

        fence = _FENCE.match(line)
        if fence:
            flush_paragraph()
            pending_field = None
            info = fence.group(3).strip()
            code_lines: list[str] = []
            marker = fence.group(2)
            i += 1
            while i < len(lines) and marker not in lines[i]:
                code_lines.append(lines[i])
                i += 1
            out.append(_render_fence(info, code_lines))
            i += 1
            continue

        heading = _HEADING.match(line)
        if heading:
            flush_paragraph()
            level = len(heading.group(1))
            text_body = heading.group(2)
            scenario_match = _SCENARIO_HEADING.match(text_body) if level == 2 else None
            if scenario_match:
                close_scenario()
                scenario_id = scenario_match.group(1)
                title = text_body[scenario_match.end() :].lstrip(" :")
                out.append('<article class="scenario">')
                out.append('<header class="scenario-head">')
                out.append(f'<p class="scenario-id">{_escape(scenario_id)}</p>')
                out.append(f"<h2>{_render_inline(title)}</h2>")
                out.append("</header>")
                out.append('<div class="scenario-body">')
                scenario_open = True
            else:
                close_scenario()
                out.append(f"<h{level}>{_render_inline(text_body)}</h{level}>")
            i += 1
            continue

        if _TABLE_ROW.match(line):
            flush_paragraph()
            pending_field = None
            table_lines: list[str] = []
            while i < len(lines) and _TABLE_ROW.match(lines[i]):
                table_lines.append(lines[i])
                i += 1
            out.append(_render_table(table_lines))
            continue

        bullet = _BULLET.match(line)
        ordered = _ORDERED.match(line)
        if bullet or ordered:
            flush_paragraph()
            pending_field = None
            tag = "ul" if bullet else "ol"
            list_class = ' class="steps"' if ordered and scenario_open else ""
            out.append(f"<{tag}{list_class}>")
            while i < len(lines):
                b = _BULLET.match(lines[i])
                o = _ORDERED.match(lines[i])
                if b:
                    out.append(
                        f"<li><span class=\"li-body\">{_render_inline(b.group(2))}</span></li>"
                    )
                    i += 1
                elif o:
                    out.append(
                        f"<li><span class=\"li-body\">{_render_inline(o.group(3))}</span></li>"
                    )
                    i += 1
                else:
                    break
            out.append(f"</{tag}>")
            continue

        if line.strip() == "":
            flush_paragraph()
            i += 1
            continue

        paragraph.append(line.strip())
        i += 1

    flush_paragraph()
    close_scenario()
    return "\n".join(out)


def _count_scenarios(path: Path) -> int:
    text_body = path.read_text(encoding="utf-8", errors="replace")
    # Count only "## ID: Title" headings, matching the renderer and validator.
    return len(re.findall(r"^##\s+[A-Z][A-Z0-9]{1,5}-\d{2,3}\s*:", text_body, re.MULTILINE))


def _read_title(readme: Path) -> str:
    for line in readme.read_text(encoding="utf-8", errors="replace").splitlines():
        match = _HEADING.match(line)
        if match:
            return match.group(2).strip()
    return "Product Playbook"


# --------------------------------------------------------------------------- #
# Print surface: minimal modern Read document.
# THESIS: hierarchy from type + whitespace, never costume labels or rails.
# OWN-WORLD: cool white paper, ink/slate neutrals, one geometric sans.
# STORY: find ID → read goal → run steps → check expected.
# --------------------------------------------------------------------------- #

CSS = """
/*
  THESIS: A printed procedure — hierarchy by type and space, not shouted labels.
  OWN-WORLD: Cool white, near-black ink, slate secondary. One sans stack.
  Refuses: cream+serif editorial, left rails, tracked uppercase field costumes.
*/
:root {
  --ink: #0e1014;
  --soft: #2e333c;
  --muted: #66707d;
  --hairline: #e2e5ea;
  --rule: #c5cad3;
  --code-tint: #f4f5f7;
  --paper: #ffffff;
  --measure: 62ch;
  --sans: "Avenir Next", "Helvetica Neue", "Segoe UI", sans-serif;
  --mono: "SF Mono", SFMono-Regular, ui-monospace, Menlo, Consolas, monospace;
  --space-1: 0.25rem;
  --space-2: 0.5rem;
  --space-3: 0.75rem;
  --space-4: 1rem;
  --space-5: 1.5rem;
  --space-6: 2.25rem;
  --space-7: 3.5rem;
}

* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }

body {
  font-family: var(--sans);
  color: var(--ink);
  background: var(--paper);
  margin: 0 auto;
  max-width: 42rem;
  padding: var(--space-7) var(--space-6) 5rem;
  line-height: 1.55;
  font-size: 16px;
  font-weight: 400;
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
}

h1, h2, h3, h4, h5, h6 {
  font-family: var(--sans);
  color: var(--ink);
  font-weight: 600;
  line-height: 1.18;
  text-wrap: balance;
  letter-spacing: -0.025em;
}
h1 {
  font-size: 2.25rem;
  letter-spacing: -0.035em;
  margin: 0 0 var(--space-4);
  max-width: 18ch;
}
h2 {
  font-size: 1.25rem;
  margin: var(--space-7) 0 var(--space-3);
}
h3 {
  font-size: 1rem;
  letter-spacing: -0.015em;
  margin: var(--space-6) 0 var(--space-2);
}
h4, h5, h6 {
  font-size: 0.9375rem;
  letter-spacing: -0.01em;
  margin: var(--space-5) 0 var(--space-2);
}

p {
  margin: 0 0 var(--space-3);
  max-width: var(--measure);
}

ul, ol {
  margin: var(--space-2) 0 var(--space-5);
  padding-left: 1.2em;
  max-width: var(--measure);
}
li {
  margin: 0.4em 0;
  break-inside: avoid;
}
li::marker { color: var(--muted); }
ol > li::marker {
  font-weight: 600;
  color: var(--soft);
  font-variant-numeric: tabular-nums;
}

strong { font-weight: 600; }

/* ---- Scenario: airy procedure unit ---- */
article.scenario {
  margin: 0;
  padding: var(--space-7) 0;
  border-top: 1px solid var(--hairline);
  break-inside: avoid;
  page-break-inside: avoid;
}
article.scenario:first-of-type {
  border-top: none;
  padding-top: var(--space-4);
}
.scenario-head {
  margin: 0 0 var(--space-4);
}
.scenario-id {
  margin: 0 0 var(--space-2);
  font-size: 0.8125rem;
  font-weight: 600;
  letter-spacing: 0.02em;
  color: var(--muted);
  font-variant-numeric: tabular-nums;
}
.scenario-head > h2 {
  margin: 0;
  font-size: 1.5rem;
  letter-spacing: -0.03em;
  line-height: 1.15;
  max-width: 22ch;
}
.scenario-body {
  margin: 0;
  max-width: var(--measure);
}
.scenario-goal {
  margin: 0 0 var(--space-3);
  font-size: 1.0625rem;
  line-height: 1.5;
  color: var(--soft);
  max-width: 36em;
}
.scenario-who {
  margin: 0 0 var(--space-2);
  font-size: 0.875rem;
  line-height: 1.45;
  color: var(--muted);
}
.scenario-who::before {
  content: "Who  ";
  font-weight: 600;
  color: var(--muted);
}
.field-label {
  margin: var(--space-6) 0 var(--space-3);
  font-size: 0.8125rem;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--ink);
}

/* Steps: hanging tabular numbers.
   IMPORTANT: each <li> must wrap copy in one .li-body child. CSS grid/flex
   otherwise treats text nodes and <strong> as separate items, shoving UI
   labels into the 2rem number column (one word per line in print). */
ol.steps {
  list-style: none;
  margin: 0 0 var(--space-5);
  padding: 0;
  counter-reset: step;
  max-width: var(--measure);
}
ol.steps > li {
  counter-increment: step;
  display: flex;
  align-items: flex-start;
  gap: var(--space-3);
  margin: 0;
  padding: 0.7rem 0;
  border-bottom: 1px solid var(--hairline);
  line-height: 1.5;
}
ol.steps > li:last-child { border-bottom: none; }
ol.steps > li::before {
  content: counter(step, decimal-leading-zero);
  flex: 0 0 1.75rem;
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.02em;
  color: var(--muted);
  font-variant-numeric: tabular-nums;
  padding-top: 0.2rem;
}
ol.steps .li-body {
  flex: 1 1 auto;
  min-width: 0;
}

.scenario-body > ul {
  list-style: none;
  margin: 0 0 var(--space-5);
  padding: 0;
  max-width: var(--measure);
}
.scenario-body > ul > li {
  position: relative;
  margin: 0;
  padding: 0.55rem 0 0.55rem 1.15rem;
  line-height: 1.5;
}
.scenario-body > ul > li::before {
  content: "";
  position: absolute;
  left: 0;
  top: 0.95em;
  width: 0.35rem;
  height: 0.35rem;
  border-radius: 50%;
  background: var(--ink);
}
.scenario-body > ul .li-body { display: inline; }

/* Tables: readable on paper, especially wide results grids */
table {
  border-collapse: collapse;
  width: 100%;
  margin: var(--space-5) 0 var(--space-6);
  font-size: 0.875rem;
  line-height: 1.4;
}
thead { break-after: avoid; }
th, td {
  border-bottom: 1px solid var(--hairline);
  padding: 0.65rem 0.7rem;
  text-align: left;
  vertical-align: top;
  overflow-wrap: anywhere;
  hyphens: auto;
}
thead th {
  border-bottom: 1px solid var(--ink);
  font-weight: 600;
  font-size: 0.75rem;
  letter-spacing: -0.01em;
  color: var(--muted);
  padding: 0.35rem 0.7rem 0.55rem;
  vertical-align: bottom;
}
tr { break-inside: avoid; }
td:first-child, th:first-child {
  padding-left: 0;
  white-space: nowrap;
  overflow-wrap: normal;
  width: 1%;
}
td:last-child, th:last-child { padding-right: 0; }

/* Wide sheets (5+ columns): denser type, still keep IDs on one line */
table:has(th:nth-child(5)) {
  font-size: 0.78rem;
}
table:has(th:nth-child(5)) th,
table:has(th:nth-child(5)) td {
  padding: 0.55rem 0.45rem;
}

.write-cell {
  min-width: 4.5rem;
  height: 2rem;
  vertical-align: bottom;
  padding-top: 0.85rem;
  padding-bottom: 0.45rem;
}
.write-line {
  display: block;
  width: 100%;
  min-width: 3.5rem;
  height: 1.15rem;
  border-bottom: 1px solid var(--rule);
}

/* Checklists */
ul.checklist {
  list-style: none;
  margin: var(--space-3) 0 var(--space-6);
  padding: 0;
  max-width: var(--measure);
}
ul.checklist > li {
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  margin: 0;
  padding: 0.7rem 0;
  border-bottom: 1px solid var(--hairline);
  font-size: 0.975rem;
  line-height: 1.35;
}
ul.checklist > li:last-child { border-bottom: none; }
ul.checklist .tick {
  flex: 0 0 auto;
  width: 0.9rem;
  height: 0.9rem;
  margin-top: 0.15rem;
  border: 1.5px solid var(--ink);
  border-radius: 0.15rem;
}
ul.checklist .label { flex: 1 1 auto; min-width: 0; }

.write-in { margin: var(--space-3) 0 var(--space-6); }
.write-in .rule {
  height: 1.75rem;
  border-bottom: 1px solid var(--rule);
}

code { font-family: var(--mono); font-size: 0.875em; }
:not(pre) > code {
  background: var(--code-tint);
  padding: 0.08em 0.35em;
  border-radius: 0.2rem;
}
pre {
  background: var(--code-tint);
  border-radius: 0.4rem;
  padding: 0.95rem 1.05rem;
  overflow-x: auto;
  line-height: 1.45;
  font-size: 0.875rem;
  break-inside: avoid;
}
pre code { background: none; padding: 0; font-size: inherit; }

a {
  color: var(--ink);
  text-decoration: none;
  border-bottom: 1px solid var(--hairline);
}
a:hover { border-bottom-color: var(--ink); }

section.chapter { break-before: page; page-break-before: always; }
section.chapter:first-of-type { break-before: auto; page-break-before: avoid; }

.hint {
  margin: 0 0 var(--space-6);
  color: var(--muted);
  font-size: 0.8125rem;
}

@page {
  size: A4;
  margin: 16mm 15mm;
  @bottom-center {
    content: counter(page);
    font-family: "Avenir Next", "Helvetica Neue", "Segoe UI", sans-serif;
    font-size: 8pt;
    color: #8a93a0;
  }
}

@media print {
  .hint { display: none; }
  body {
    padding: 0;
    max-width: none;
    font-size: 10.5pt;
  }
  a { border-bottom: none; }
  .scenario-head > h2 { max-width: none; }
  h1 { max-width: none; }
  /* Results and coverage grids need the full text block. */
  table { font-size: 8.5pt; }
  table:has(th:nth-child(5)) { font-size: 8pt; }
  th, td { padding: 0.45rem 0.4rem; }
  .write-cell { height: 1.85rem; }
}
"""


def _wrap_document(sections: Iterable[str], title: str = "Product Playbook") -> str:
    safe_title = _escape(title)
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{safe_title}</title>\n"
        f"<style>{CSS}</style>\n"
        "</head>\n"
        "<body>\n"
        f'<div class="hint">{safe_title} &middot; print to PDF from your browser&rsquo;s Print dialog.</div>\n'
        + "\n".join(sections)
        + "\n</body>\n</html>\n"
    )


def build_html(files: list[Path]) -> tuple[str, int, int]:
    chapters = files[1:-1]
    scenario_total = sum(_count_scenarios(path) for path in chapters)
    sections: list[str] = []
    for path in files:
        body = path.read_text(encoding="utf-8", errors="replace")
        anchor = _file_anchor(path)
        sections.append(
            f'<section id="{anchor}" class="chapter">'
            f"{render_markdown(body)}"
            "</section>"
        )
    document = _wrap_document(sections, _read_title(files[0]))
    return document, len(chapters), scenario_total


# --------------------------------------------------------------------------- #
# PDF conversion: print the HTML to PDF and delete the intermediate HTML.
# Standard library only; relies on an external converter binary if present.
# --------------------------------------------------------------------------- #

def _find_chrome() -> Optional[str]:
    candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    ]
    for candidate in candidates:
        if Path(candidate).is_file():
            return candidate
    for name in (
        "google-chrome-stable",
        "google-chrome",
        "chromium",
        "chromium-browser",
        "chrome",
    ):
        path = shutil.which(name)
        if path:
            return path
    return None


def _pdf_looks_valid(pdf_path: Path) -> bool:
    try:
        return pdf_path.is_file() and pdf_path.read_bytes()[:4] == b"%PDF"
    except OSError:
        return False


def _discard_invalid_pdf(pdf_path: Path) -> None:
    try:
        if pdf_path.exists():
            pdf_path.unlink()
    except OSError:
        pass


def _run_converter(name: str, cmd: list[str], pdf_path: Path) -> Optional[str]:
    """Run one converter. Return None on success, else a short failure reason."""
    _discard_invalid_pdf(pdf_path)
    try:
        completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except OSError as error:
        return f"{name}: failed to start ({error})"
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        if detail:
            detail = detail.splitlines()[-1][:300]
            return f"{name}: exit {completed.returncode}: {detail}"
        return f"{name}: exit {completed.returncode}"
    if not _pdf_looks_valid(pdf_path):
        _discard_invalid_pdf(pdf_path)
        return f"{name}: produced no valid PDF"
    return None


def _html_to_pdf(html_path: Path, pdf_path: Path) -> None:
    """Print a single HTML file to PDF using the first available converter.

    Chromium-based browsers need ``--no-sandbox`` / ``--disable-dev-shm-usage``
    on typical Linux CI runners. Only report "no PDF converter found" when none
    were present; otherwise surface the converter stderr so CI can diagnose.
    Intermediate HTML is owned by the caller and is only deleted after a valid
    PDF is written (see ``export_pdf``).
    """
    attempts: list[str] = []
    chrome = _find_chrome()
    if chrome:
        # Prefer new headless; fall back to classic if the binary rejects it.
        for headless_flag in ("--headless=new", "--headless"):
            error = _run_converter(
                Path(chrome).name,
                [
                    chrome,
                    headless_flag,
                    "--disable-gpu",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--no-pdf-header-footer",
                    f"--print-to-pdf={pdf_path}",
                    html_path.as_uri(),
                ],
                pdf_path,
            )
            if error is None:
                return
            attempts.append(error)

    wkhtmltopdf = shutil.which("wkhtmltopdf")
    if wkhtmltopdf:
        error = _run_converter(
            "wkhtmltopdf",
            [wkhtmltopdf, "-q", str(html_path), str(pdf_path)],
            pdf_path,
        )
        if error is None:
            return
        attempts.append(error)

    pandoc = shutil.which("pandoc")
    if pandoc:
        error = _run_converter(
            "pandoc",
            [pandoc, str(html_path), "-o", str(pdf_path)],
            pdf_path,
        )
        if error is None:
            return
        attempts.append(error)

    if not attempts:
        raise ValueError(
            "no PDF converter found. Install Google Chrome, Chromium, wkhtmltopdf, "
            "or pandoc, or run with --format html and print to PDF from a browser."
        )
    raise ValueError(
        "PDF conversion failed. Tried: " + "; ".join(attempts)
    )


def export_pdf(files: list[Path], target: Path) -> tuple[int, int]:
    html_text, chapter_count, scenario_total = build_html(files)
    with tempfile.TemporaryDirectory(prefix="product-playbook-") as tmp:
        html_path = Path(tmp) / "playbook.html"
        html_path.write_text(html_text, encoding="utf-8")
        _html_to_pdf(html_path, target)
    return chapter_count, scenario_total


def export_html(files: list[Path], target: Path) -> tuple[int, int]:
    html_text, chapter_count, scenario_total = build_html(files)
    target.write_text(html_text, encoding="utf-8")
    return chapter_count, scenario_total


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir).expanduser().resolve()
    default_name = "playbook.pdf" if args.format == "pdf" else "playbook.html"
    target = (
        Path(args.output).expanduser().resolve()
        if args.output
        else output_dir / default_name
    )
    try:
        files = collect_files(output_dir)
        if target.exists() and not args.force:
            raise ValueError(f"destination already exists: {target} (use --force to overwrite)")
        if args.format == "pdf":
            chapter_count, scenario_total = export_pdf(files, target)
        else:
            chapter_count, scenario_total = export_html(files, target)
    except ValueError as error:
        raise SystemExit(str(error)) from error
    print(
        json.dumps(
            {
                "output_path": str(target),
                "format": args.format,
                "files": [path.name for path in files],
                "chapters": chapter_count,
                "scenarios": scenario_total,
                "intermediate_html_kept": args.format == "html",
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
