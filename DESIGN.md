# Design

Visual system for the opt-in playbook export (`playbook.html` / `playbook.pdf`).
Markdown remains the source of truth; this file covers the derived print surface only.

## Mode

**Read** — a tester at a desk under bright light, marking pass/fail on paper or PDF.

## Direction

**Thesis:** Hierarchy comes from type size, weight, and whitespace — never from costume labels, left rails, or code-block chrome.

**World:** Cool white paper, near-black ink, slate secondary. One geometric sans stack for the whole document. No cream ground, no terracotta, no purple, no broadsheet hairline columns, no neon-on-dark.

**Story:** Find the scenario ID, read the goal as context, execute steps, confirm expected results, tick the checklist.

## Type

| Role | Treatment |
| --- | --- |
| Chapter title | Large, tight tracking, weight 600 |
| Scenario ID | Small, muted, tabular |
| Scenario title | Clearly larger than body; the page peak |
| Goal | Soft dek under the title — no “GOAL” shout |
| Who | Quiet meta line |
| Field labels (Steps, Expected, …) | Sentence case, ink, space above > space below |
| Body / steps | Comfortable measure (~65ch), generous leading |
| Code | Mono only for real code |

Stack: `"Avenir Next", "Helvetica Neue", "Segoe UI", sans-serif` (local, no webfonts).

## Space

- Breathing room between scenarios; hairline only as a soft separator
- Tight within a field; generous before the next field
- No indent rail beside scenario bodies
- Empty cells and note fences render as write-in lines, not empty gray boxes

## Color

Restrained neutrals only:

- Ink `#0e1014`
- Soft `#2e333c`
- Muted `#66707d`
- Hairline `#e2e5ea`
- Paper `#ffffff`
