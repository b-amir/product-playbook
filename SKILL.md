---
name: product-playbook
description: >-
  Create, reconcile, audit, or agent-check evidence-backed manual testing playbooks
  from any product codebase (tests, contracts, Swagger, docs, source, live interfaces).
  Use when the user asks for a product playbook, manual QA playbook, UAT script,
  tester-facing scenarios, playbook reconciliation, playbook audit, or drift check
  against an existing playbook. Optionally also generates runnable e2e/API/CLI
  tests that share the scenario IDs, with targets, safety tags, acceptance-example
  traceability, and a pasteable run summary. Do not use for writing unit tests, designing APIs,
  or generic QA strategy without a repository. Never invent interface labels or
  behavior. Publish only tester-facing Markdown plus one portable state JSON;
  optional PDF/HTML and sibling findings only when asked.
---

# Product Playbook

Build one canonical **tester-facing** Markdown playbook from runtime evidence for any
product shape (web, API, CLI, worker, RAG, mobile, SDK, mixed, monorepo, or multi-repo).

Follow [references/run-protocol.md](references/run-protocol.md) on every run. Same phases,
Intake Card (text only, no polls), Plan gate, and End Report — every harness.

## Non-negotiables

- Classify the product **first**, then choose probes. No frontend-only default.
- Never invent visible labels, endpoints, commands, or outcomes.
- Playbook directory contains only Markdown chapters plus
  `.product-playbook-state.json` (fingerprints only — no verification history, issues, or todos).
- PDF/HTML only on explicit ask → [references/export.md](references/export.md).
- Agent-check findings → sibling `playbook-findings/` only →
  [references/agent-check.md](references/agent-check.md).
- Runnable tests are opt-in, live in sibling `playbook-tests/`, and automate only
  evidence-backed steps → [references/tests.md](references/tests.md).
- Credentials only as env var names. Prod targets run only `smoke`/`safe` tests by default.
- Never embed org names, people, machine paths, or product-specific assumptions in this skill.

## Run status (show at the start of each phase)

This is the **workflow position for this chat**, not a product checklist and not
playbook chapter ticks. Update the marks as you move. Do not invent extra phases.

```text
Run status (this chat):
- [x] 1. Intake — done bootstrap; waiting for your letter reply (no files written)
- [ ] 2. Plan — not started (starts after Intake answers)
- [ ] 3. Write — not started (starts after you approve the plan; includes runnable tests if opted in)
- [ ] 4a. Export PDF/HTML — optional; skipped unless you ask
- [ ] 4b. Agent-check — optional; skipped unless you ask
```

Meaning of marks:
- `[x]` = finished for this run, or currently waiting on you at that step
- `[ ]` = not started yet, or optional and not requested

After the user answers Intake, flip Plan to in-progress before showing the plan table.
After Plan approval, flip Write before patching files.
Leave 4a/4b unchecked unless the user explicitly asks for them.

## Inputs

Require at least one evidence source. Locations are runtime-only:

```text
SOURCE_ID=PATH_OR_URL
```

Stable IDs describe responsibility (`web`, `api`, `docs`, …), not branding.

A source path is **not** assumed to be one git repository. Workspace folders that contain
nested repos, submodules, or product-looking subfolders (`frontend/`, `backend/`,
`unified-docs/`, …) are expanded into separate scan roots before discovery. Intake Folders
lists those members — not a single wrapper pretending to be the whole product.

Also accept: `docs_source`, `output_dir`, `draft_path`, `run_scope`
(`auto` | `full` | `contribution` | `audit`), `scope`, `product_surface`,
`test_framework`, `verify` / Agent-check, propose-only plan path, inventory
`--drift` for CI exit codes, `runnable_tests` (opt-in), `target`, and an acceptance-examples file.

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

Present Intake as **one chat message** per [references/intake.md](references/intake.md).

Hard rules:

1. Run `bootstrap_playbook.py` (prefer explicit `--source` / `--docs-source`).
2. **No polls / AskQuestion for Intake.**
3. Print `intake.intake_message` **verbatim**. Do not rewrite or invent table rows.
4. Preserve every blank line, heading, and list break from that message. Never collapse
   choices onto one line.
5. Same sources → same Intake. If two chats disagree, compare the Scope row first.

Polls are allowed later only for Plan approve and after-Plan picks.
Stop until the user answers with letters or `recommended`.
Never ask about digests, fingerprints, or session IDs.
Never ask them to write sentences when a letter will do.

Destination policy: explicit `output_dir` / `draft_path` → unique discovered playbook →
propose `<source>/docs/playbook` when one local code source → else ask.
Never merge divergent drafts. Never fork a product-wide docs playbook per repo.

Contribution rules: [references/collaboration-state.md](references/collaboration-state.md).

## 2. Discover and inventory

Read [references/framework-discovery.md](references/framework-discovery.md) for the detected
surfaces. Expand probes (SSO, webhooks, flags, i18n, a11y, viewport forks) only when evidence
exists.

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

When runnable tests were opted in, add a **Test** column: `auto: smoke|safe|destructive`, or
`manual-only: <reason>`, plus mapped acceptance IDs. Record it in the plan as
`automated_tests` and per-scenario `automation` (see [references/tests.md](references/tests.md)).

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

When runnable tests are opted in, follow the Write-phase checklist in
[references/tests.md](references/tests.md):

```bash
python3 <skill-dir>/scripts/playbook_tests.py import-acceptance "<tests_dir>" "<examples.md>"  # optional
python3 <skill-dir>/scripts/playbook_tests.py fingerprint "<tests_dir>" --source "SOURCE_ID=<root>"
python3 <skill-dir>/scripts/validate_playbook.py "<output_dir>" --tests-dir "<tests_dir>"
python3 <skill-dir>/scripts/playbook_tests.py run "<tests_dir>" --target local
```

Paste the run summary into the End Report. Keep **E** (Blocked, environment) apart from **F**:
missing cloud services, queues, or paid models are environment issues
([references/environments.md](references/environments.md)). Before calling **F**, run the
readiness check: the feature exists in the code and, when a ticket is known, the ticket is ready
for testing; otherwise record **U** (Not built yet). Ticket-pinned runs, run history, `retest`
and `changed` (what to rerun) are in [references/runs.md](references/runs.md). When unclear,
use its judgment defaults and state each assumption. Never write to a tracker or chat unless
asked. One-page entry point for people and agents: [QUICKSTART.md](QUICKSTART.md). Drift: add `--tests-dir` to inventory `--drift`.

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
