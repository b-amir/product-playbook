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


def _render_inline(text: str) -> str:
    placeholders: list[str] = []

    def stash_code(match: "re.Match[str]") -> str:
        placeholders.append(f"<code>{_escape(match.group(1))}</code>")
        return f"\x00{len(placeholders) - 1}\x00"

    work = _CODE_SPAN.sub(stash_code, text)
    work = _BOLD.sub(r"<strong>\1</strong>", work)

    def render_link(match: "re.Match[str]") -> str:
        label = match.group(1)
        target = match.group(2).strip()
        if target.endswith(".md") and "/" not in target and "#" not in target:
            anchor = slugify(Path(target).stem)
            return f'<a href="#{anchor}">{_escape(label)}</a>'
        return (
            f'<a href="{_escape(target)}" target="_blank" '
            f'rel="noopener noreferrer">{_escape(label)}</a>'
        )

    work = _LINK.sub(render_link, work)
    work = _escape(work)
    work = re.sub(
        r"\x00(\d+)\x00",
        lambda m: placeholders[int(m.group(1))],
        work,
    )
    work = work.replace("&lt;strong&gt;", "<strong>").replace("&lt;/strong&gt;", "</strong>")
    work = work.replace("&lt;a ", "<a ").replace("&lt;/a&gt;", "</a>")
    return work


def _render_table(rows: list[str]) -> str:
    cells = [
        [cell.strip() for cell in row.strip().strip("|").split("|")]
        for row in rows
    ]
    if len(cells) < 2:
        return "".join(f"<p>{_render_inline(row)}</p>" for row in rows)
    header = cells[0]
    out = ["<table>", "<thead><tr>"]
    out.extend(f"<th>{_render_inline(cell)}</th>" for cell in header)
    out.append("</tr></thead><tbody>")
    body_rows = cells[2:] if (len(cells) > 2 and _TABLE_SEP.match(cells[1][0])) else cells[1:]
    for row in body_rows:
        if all(re.fullmatch(r":?-{2,}:", cell or "-") for cell in row):
            continue
        out.append("<tr>")
        out.extend(f"<td>{_render_inline(cell)}</td>" for cell in row)
        out.append("</tr>")
    out.append("</tbody></table>")
    return "".join(out)


def render_markdown(body: str) -> str:
    lines = body.splitlines()
    out: list[str] = []
    i = 0
    paragraph: list[str] = []
    scenario_open = False

    def flush_paragraph() -> None:
        if paragraph:
            out.append(f"<p>{_render_inline(' '.join(paragraph))}</p>")
            paragraph.clear()

    def close_scenario() -> None:
        nonlocal scenario_open
        if scenario_open:
            out.append("</div></article>")
            scenario_open = False

    while i < len(lines):
        line = lines[i]

        fence = _FENCE.match(line)
        if fence:
            flush_paragraph()
            info = fence.group(3).strip()
            code_lines: list[str] = []
            marker = fence.group(2)
            i += 1
            while i < len(lines) and marker not in lines[i]:
                code_lines.append(lines[i])
                i += 1
            lang_class = f' class="language-{_escape(info)}"' if info else ""
            out.append(f"<pre><code{lang_class}>{_escape(chr(10).join(code_lines))}</code></pre>")
            i += 1
            continue

        heading = _HEADING.match(line)
        if heading:
            flush_paragraph()
            level = len(heading.group(1))
            text_body = heading.group(2)
            # A scenario ("## ID: Title") is a self-contained work unit. Its
            # following content is wrapped in .scenario-body so CSS can indent the
            # whole procedure as one level under the scenario heading.
            if level == 2 and _SCENARIO_HEADING.match(text_body):
                close_scenario()
                out.append('<article class="scenario">')
                out.append(f"<h2>{_render_inline(text_body)}</h2>")
                out.append('<div class="scenario-body">')
                scenario_open = True
            else:
                close_scenario()
                out.append(f"<h{level}>{_render_inline(text_body)}</h{level}>")
            i += 1
            continue

        if _TABLE_ROW.match(line):
            flush_paragraph()
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
            tag = "ul" if bullet else "ol"
            out.append(f"<{tag}>")
            while i < len(lines):
                b = _BULLET.match(lines[i])
                o = _ORDERED.match(lines[i])
                if b:
                    out.append(f"<li>{_render_inline(b.group(2))}</li>")
                    i += 1
                elif o:
                    out.append(f"<li>{_render_inline(o.group(3))}</li>")
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
# Typography: a deliberately scaled, indented, hierarchical system for a Read surface.
# --------------------------------------------------------------------------- #

CSS = """
:root {
  --ink: #14161a;
  --soft: #3d424b;
  --muted: #6b717c;
  --hairline: #d6d9df;
  --hairline-soft: #ecedf1;
  --code-tint: #f3f4f7;
  --paper: #ffffff;
  --indent: 28px;
}

* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }

body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  color: var(--ink);
  background: var(--paper);
  margin: 0 auto;
  max-width: 760px;
  padding: 56px 44px 96px;
  line-height: 1.62;
  font-size: 10.5pt;
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
}

/* ---- Type scale: a real ratio (~1.25), distinct weight per role ---- */
h1, h2, h3, h4, h5, h6 {
  line-height: 1.22;
  color: var(--ink);
  letter-spacing: -0.012em;
}
h1 {
  font-size: 30pt;
  font-weight: 700;
  letter-spacing: -0.03em;
  line-height: 1.12;
  margin: 0 0 0.4em;
}
h2 {
  font-size: 18pt;
  font-weight: 700;
  letter-spacing: -0.02em;
  margin: 2.2em 0 0.5em;
}
h3 {
  font-size: 13pt;
  font-weight: 600;
  margin: 1.8em 0 0.45em;
}
h4 {
  font-size: 11pt;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--soft);
  margin: 1.5em 0 0.35em;
}
h5, h6 { font-size: 10.5pt; font-weight: 600; margin: 1.3em 0 0.35em; }

p { margin: 0 0 0.8em; }

/* ---- Lists: ordered steps carry the procedure ---- */
ul { margin: 0.2em 0 1em; padding-left: 1.25em; }
ol { margin: 0.3em 0 1.1em; padding-left: 1.55em; }
li { margin: 0.4em 0; break-inside: avoid; }
ul > li { margin: 0.26em 0; }
li::marker { color: var(--muted); }
ol > li::marker { font-weight: 700; color: var(--ink); }

strong { font-weight: 680; }

/* ---- Scenario: self-contained unit, indented body, never split ---- */
article.scenario {
  margin-top: 2.4em;
  padding-top: 1.9em;
  border-top: 1px solid var(--hairline);
  break-inside: avoid;
  page-break-inside: avoid;
}
article.scenario:first-of-type { margin-top: 0.5em; }
article.scenario > h2 {
  margin-top: 0;
  font-size: 14pt;
  font-weight: 700;
  letter-spacing: -0.015em;
}

/* Scenario body indented one level: the procedure sits under its heading. */
.scenario-body {
  margin-left: var(--indent);
  margin-top: 0.6em;
  padding-left: 4px;
  border-left: 2px solid var(--hairline-soft);
}
.scenario-body > p:first-child { margin-top: 0; }

/* A standalone bold label line ("**Goal**" alone in a paragraph) becomes a
   distinct field label: uppercase, tracked, muted, tight below its value. */
.scenario-body > p:has(> strong:only-child) {
  margin: 1.2em 0 0.15em;
}
.scenario-body > p > strong:only-child {
  display: inline-block;
  color: var(--muted);
  font-weight: 700;
  font-size: 8pt;
  text-transform: uppercase;
  letter-spacing: 0.13em;
}

/* ---- Tables: hairlines only ---- */
table {
  border-collapse: collapse;
  width: 100%;
  margin: 1.3em 0 1.7em;
  font-size: 9.75pt;
}
thead { break-after: avoid; }
th, td {
  border-top: 1px solid var(--hairline);
  border-bottom: 1px solid var(--hairline);
  padding: 9px 11px;
  text-align: left;
  vertical-align: top;
}
thead th {
  border-top: none;
  border-bottom: 1.5px solid var(--ink);
  font-weight: 700;
  font-size: 8.75pt;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--soft);
}
tr { break-inside: avoid; }

/* ---- Code: quiet tint ---- */
code {
  font-family: ui-monospace, "SF Mono", SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
  font-size: 0.9em;
}
:not(pre) > code {
  background: var(--code-tint);
  padding: 1px 5px;
  border-radius: 3px;
}
pre {
  background: var(--code-tint);
  border-radius: 6px;
  padding: 13px 15px;
  overflow-x: auto;
  line-height: 1.5;
  font-size: 9.25pt;
  break-inside: avoid;
}
pre code { background: none; padding: 0; font-size: inherit; }

/* ---- Links ---- */
a { color: var(--ink); text-decoration: none; border-bottom: 1px solid var(--hairline); }
a:hover { border-bottom-color: var(--ink); }

/* ---- Chapter pagination ---- */
section.chapter { break-before: page; page-break-before: always; }
section.chapter:first-of-type { break-before: auto; page-break-before: avoid; }

/* ---- Print hint: screen-only ---- */
.hint {
  margin: 0 0 44px;
  padding: 11px 15px;
  border-radius: 7px;
  background: var(--hairline-soft);
  color: var(--muted);
  font-size: 9pt;
}

@page {
  size: A4;
  margin: 20mm 18mm;
  @bottom-center { content: counter(page); font-size: 8.5pt; color: #9aa0a8; }
}

@media print {
  .hint { display: none; }
  body { padding: 0; max-width: none; }
  a { border-bottom: none; }
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
