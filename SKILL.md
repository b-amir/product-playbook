---
name: product-playbook
description: >-
  Create, reconcile, audit, or agent-check evidence-backed manual testing playbooks
  from any product codebase (tests, contracts, Swagger, docs, source, live interfaces).
  Use when the user asks for a product playbook, manual QA playbook, UAT script,
  tester-facing scenarios, playbook reconciliation, playbook audit, or drift check
  against an existing playbook. Do not use for writing unit tests, designing APIs,
  or generic QA strategy without a repository. Never invent interface labels or
  behavior. Publish only tester-facing Markdown plus one portable state JSON;
  optional PDF/HTML and sibling findings only when asked.
---

# Product Playbook

Build one canonical **tester-facing** Markdown playbook from runtime evidence for any
product shape (web, API, CLI, worker, RAG, mobile, SDK, mixed, monorepo, or multi-repo).

Follow [references/run-protocol.md](references/run-protocol.md) on every run. Same phases,
Intake Card, polls, Plan gate, and End Report — every harness.

## Non-negotiables

- Classify the product **first**, then choose probes. No frontend-only default.
- Never invent visible labels, endpoints, commands, or outcomes.
- Playbook directory contains only Markdown chapters plus
  `.product-playbook-state.json` (fingerprints only — no verification history, issues, or todos).
- PDF/HTML only on explicit ask → [references/export.md](references/export.md).
- Agent-check findings → sibling `playbook-findings/` only →
  [references/agent-check.md](references/agent-check.md).
- Never embed org names, people, machine paths, or product-specific assumptions in this skill.

## Task progress (copy each run)

```text
- [ ] 1. Intake (bootstrap; Intake Card + polls; no writes)
- [ ] 2. Plan (Keep/Update/Add/… table; wait for approval)
- [ ] 3. Write (patch/render → validate → state → End Report)
- [ ] 4a. Export PDF/HTML (only if asked)
- [ ] 4b. Agent-check (only if asked; do everything safely possible)
```

## Inputs

Require at least one evidence source. Locations are runtime-only:

```text
SOURCE_ID=PATH_OR_URL
```

Stable IDs describe responsibility (`web`, `api`, `docs`, …), not branding.

Also accept: `docs_source`, `output_dir`, `draft_path`, `run_scope`
(`auto` | `full` | `contribution` | `audit`), `scope`, `product_surface`,
`test_framework`, `verify` / Agent-check, propose-only plan path, and inventory
`--drift` for CI exit codes.

## 1. Intake

When intent, source, or destination is unclear:

```bash
python3 <skill-dir>/scripts/bootstrap_playbook.py
```

Or with explicit sources:

```bash
python3 <skill-dir>/scripts/bootstrap_playbook.py \
  --source "product=<path-or-url>" \
  --intent auto
```

Present the **Intake Card** and **one poll round** per
[references/intake.md](references/intake.md). Prefer the harness structured-choice UI;
fall back to one numbered list. Stop until the user answers.

Destination policy: explicit `output_dir` / `draft_path` → unique discovered playbook →
propose `<source>/docs/playbook` when one local code source → else ask.
Never merge divergent drafts. Never fork a product-wide docs playbook per repo.

Contribution rules: [references/collaboration-state.md](references/collaboration-state.md).

## 2. Discover and inventory

Read [references/framework-discovery.md](references/framework-discovery.md) for the detected
surfaces. Expand probes (SSO, webhooks, flags, i18n, a11y) only when evidence exists.

When a draft exists:

```bash
python3 <skill-dir>/scripts/inventory_playbook.py "<output_dir>" \
  --source "SOURCE_ID=<root>" \
  --run-scope contribution \
  --scope "SOURCE_ID" \
  --check-state
```

Capture `state_digest`. Use `impacted_scenarios`, `reusable_scenarios`,
`changed_sources`, `changed_paths_by_source`, and `preserved_out_of_scope`.

Drift / CI mode (exit `1` when impact exists):

```bash
python3 <skill-dir>/scripts/inventory_playbook.py "<output_dir>" \
  --source "SOURCE_ID=<root>" \
  --check-state --drift
```

## 3. Evidence rules

Priority for each claim:

1. Successful current observation
2. Passing current e2e/integration test
3. Current test source (not executed)
4. Contract + application source
5. Technical documentation
6. Existing playbook prose

Statuses `VERIFIED` / `SOURCED` / `UNRESOLVED` stay in chat and the temporary ledger only.
Validate plans and ledgers:

```bash
python3 <skill-dir>/scripts/schema_utils.py plan.json --kind plan
python3 <skill-dir>/scripts/schema_utils.py ledger.json --kind ledger
```

Schemas: [schemas/plan.schema.json](schemas/plan.schema.json),
[schemas/ledger.schema.json](schemas/ledger.schema.json).
Examples: [examples.md](examples.md).

## 4. Plan (hard stop)

Classify Keep / Update / Split / Merge / Remove / Add / Needs more evidence.
Present the plan table. Wait for Approve / Adjust / Audit-only.

Propose-only (no Markdown write):

```bash
python3 <skill-dir>/scripts/propose_plan.py "<plan.json>" "<review-plan.json>"
```

## 5. Write

Read [references/output-contract.md](references/output-contract.md) and
[references/draft-reconciliation.md](references/draft-reconciliation.md).

```bash
python3 <skill-dir>/scripts/render_playbook.py "<plan.json>" "<output_dir>"
# or patch an existing draft in place

python3 <skill-dir>/scripts/validate_playbook.py "<output_dir>"

python3 <skill-dir>/scripts/inventory_playbook.py "<output_dir>" \
  --source "SOURCE_ID=<root>" \
  --run-scope contribution \
  --scope "SOURCE_ID" \
  --evidence-ledger "<ledger.json>" \
  --base-state-digest "<digest>" \
  --write-state

python3 <skill-dir>/scripts/validate_playbook.py "<output_dir>" --require-state
```

Emit the End Report from [references/run-protocol.md](references/run-protocol.md).

## 6. Export (opt-in)

[references/export.md](references/export.md)

## 7. Agent-check (opt-in)

Do everything safely possible: playbook smoke, live Swagger/API, UI/CLI/device tools,
and repository tests. Write findings only under `<playbook-parent>/playbook-findings/`.
Full rules: [references/agent-check.md](references/agent-check.md).

## Companions

Narrow entry points (same scripts and rules):

- [companions/product-playbook-audit/SKILL.md](companions/product-playbook-audit/SKILL.md)
- [companions/product-playbook-export/SKILL.md](companions/product-playbook-export/SKILL.md)
