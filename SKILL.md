---
name: product-playbook
description: Create or reconcile evidence-backed manual testing and product-usage playbooks for frontend, API, backend, full-stack, CLI, service, worker, integration, and mobile projects. Use when discovering product journeys from automated tests, contracts, source, docs, and optional live verification, fact-checking or incrementally updating an existing draft, or when the user mentions product playbook, manual testing playbook, test documentation, or playbook reconciliation. Never invent UI labels, endpoints, commands, roles, events, routes, or behavior. Output must stay tester-facing.
license: MIT
compatibility: Requires Python 3.9+ for bundled helper scripts. Works with any product that has tests, contracts, or observable interfaces.
metadata:
  version: "1.0.0"
---

# Product Playbook

Generate a portable Markdown playbook that a tester, product owner, support person, operator,
manager, or administrator can execute through the product's supported interface.

The published Markdown is **tester-facing only**. Keep evidence ledgers, status labels, source maps,
reconciliation history, and unresolved-gap notes in the agent conversation or in
`.product-playbook-state.json`. Never put those into the playbook the tester reads.

## Collect inputs and choose a mode

Require:

- `code_repo`: One or more local paths or URLs containing product code and tests
- `docs_repo` or `docs_path`: Supporting documentation, or explicit confirmation that none exists

Accept:

- `product_surface`: `auto`, `frontend`, `api`, `fullstack`, `cli`, `service`, or `mobile`
- `test_framework`: One framework, multiple frameworks, or `auto`
- `draft_path`: Explicit existing playbook
- `output_dir`: Canonical playbook directory for this product
- `mode`: `auto`, `create`, or `reconcile`
- `verify` or `run_tests`: Whether to execute tests or drive a supported interface

Resolve repository URLs to read-only temporary checkouts. Do not change source repositories.

### Destination policy (product-neutral)

The playbook is a **product** artifact. Evidence roots (`code_repo`, `docs_path`) are inputs only.
Never hardcode product names, company names, or docs-repo brand names. Paths come from the user or
from portable defaults below.

Resolve the write destination in this order:

1. Explicit `output_dir`.
2. Explicit `draft_path` (directory, or parent of a playbook file).
3. Exactly one discovered playbook candidate under the given roots → reuse it (reconcile).
4. Otherwise, if there is exactly one `code_repo` and **no** `docs_path` →  
   `<that-code-repo>/docs/playbook`.
5. Otherwise **stop and ask** for `output_dir` before writing. Typical cases:
   - multiple `code_repo` roots
   - one or more `docs_path` roots and no unique draft
   - multiple playbook candidates

When asking, explain that later runs (other repos, other teammates) should pass the **same**
`output_dir` so journeys reconcile into one tester-facing playbook. Suggest a shared docs or product
repo path only as an example shaped like `<docs-repo>/playbook`. Do not invent a repo name.

Also ask before writing when multiple credible drafts exist. Never merge drafts automatically. Never
create a second playbook for the same product only because a new evidence root appeared.

Choose `reconcile` when a draft exists at the chosen destination. Choose `create` only when
discovery finds no draft there or the user explicitly requests a fresh output.

### Multi-root reconcile

When another code or docs root is added later, run against the **same** `output_dir`:

- Keep scenarios whose user outcome still holds.
- Update steps and expected results from the new evidence.
- Add journeys the new root uniquely proves.
- Merge FE and API views of one journey into one scenario when the tester still operates one
  interface flow.
- Do not rewrite the whole playbook and do not publish merge history in the Markdown.


## Enforce evidence rules

1. Treat current automated end-to-end, integration, contract, API, CLI, service, or mobile tests as
   primary behavioral evidence.
2. Treat executable contracts and application source as supporting evidence.
3. Treat technical docs as terminology and context that can drift.
4. Treat successful current observation through the supported interface as the strongest evidence.
5. Treat existing playbook prose as a candidate to reconcile, never as independent evidence.
6. Copy visible labels, endpoints, methods, fields, commands, options, events, statuses, and
   observable outcomes exactly from evidence.
7. Resolve missing or conflicting details yourself before writing. Prefer source, contracts, tests,
   and safe observation. If a detail still cannot be established, omit it, ask the user in chat, or
   move the prerequisite into Environment handoff. Do **not** publish gap markers, status labels, or
   conflict notes in the playbook.
8. Surface conflicts to the user in the planning message when needed. Write only the resolved
   tester-facing procedure into the playbook.
9. Keep raw source paths and technical traceability in `.product-playbook-state.json` and in the
   agent report. Do not add chapter Sources tables or a hub verification index.

Internal evidence statuses (conversation and state only, never in playbook Markdown):

- `VERIFIED`: The complete scenario passed now through execution or successful observation.
- `SOURCED`: Every required detail traces to current evidence, but the complete scenario was not
  executed now.
- `UNRESOLVED`: A required detail is missing, conflicting, failing, or inferred. Do not publish the
  scenario or that detail until resolved or explicitly scoped out with the user.

Downgrade old `VERIFIED` state entries to `SOURCED` unless they pass during the current run.

## Run the phased pipeline

Keep each phase distinct. Report the phase transition and its artifact **to the user in chat**. Do
not write pipeline history into the playbook files.

### 1. Discover

1. Read repository instructions such as `AGENTS.md`.
2. Run the discovery helper, repeating `--code-repo` and `--docs-path` when needed:

   ```bash
   python3 <skill-dir>/scripts/discover_product.py \
     --code-repo "<code_repo>" \
     --docs-path "<docs_path>" \
     --product-surface auto
   ```

3. Confirm languages, product surfaces, test frameworks, test commands, test directories,
   interfaces, contracts, roles, documentation roots, existing playbook candidates, and the
   discovery fields `output_decision`, `ask_before_write`, and `recommended_output_dir`.
4. If `ask_before_write` is true, stop and ask the user for the destination (or which draft) before
   any generate step.
5. Read [references/framework-discovery.md](references/framework-discovery.md) for the detected
   surface.
6. Override auto-detection only when evidence shows it is wrong.
7. Exclude dependencies, generated code, builds, coverage, and test artifacts.

If discovery finds multiple drafts, stop and ask which is authoritative.

### 2. Inventory the draft

Skip this phase only in create mode.

Read [references/draft-reconciliation.md](references/draft-reconciliation.md), then run:

```bash
python3 <skill-dir>/scripts/inventory_playbook.py "<draft_path>" \
  --code-repo "<code_repo>" \
  --docs-path "<docs_path>" \
  --check-state
```

Use the compact inventory before loading full chapter prose.

If no `.product-playbook-state.json` exists, perform a full factual audit while preserving useful
wording and IDs. If valid state exists, reuse only scenarios listed as reusable. Re-audit impacted
scenarios and run a coverage scan whenever a source root changed.

Never use state to skip:

- New or removed journey discovery
- Changed shared fixtures, authentication, permissions, contracts, routes, or configuration
- Unresolved scenarios
- Whole-output validation

### 3. Analyze

For every candidate or impacted scenario:

1. Record the suite and test title.
2. Extract preconditions, actor or identity, ordered actions, assertions, cleanup, and failure
   behavior.
3. Trace helpers, fixtures, mocks, contracts, and access checks that affect observable behavior.
4. Resolve exact interface terms from accessible UI, executable contracts, help output, schemas,
   source, or observation.
5. Separate user or operator workflows from implementation-only unit tests.
6. Record source conflicts and failures in the agent ledger. Do not leave assumptions in the
   published steps.

Build or update an evidence ledger in the agent workspace only:

| Candidate | Actor | Interface | Actions source | Assertions source | Execution | Status | Gaps |
| --------- | ----- | --------- | -------------- | ----------------- | --------- | ------ | ---- |

For API scenarios, establish exact methods, paths, request fields, identity, status codes, and
observable response properties. For CLI, service, worker, event, webhook, or mobile scenarios,
establish a supported trigger and observable result.

### 4. Reconcile or plan

In reconcile mode, classify every existing scenario as:

- Keep
- Update
- Split
- Merge
- Remove
- Needs more evidence

Add scenarios revealed by current evidence. Preserve an ID when the user outcome remains materially
the same. Explain removals and ID changes **in chat**, not in the playbook.

In both modes:

1. Group scenarios by real journey.
2. Include only applicable authentication, administration, access, integration, and quality areas.
3. Adapt the quality sweep to the surface.
4. Prioritize a minimal smoke path.
5. Present the coverage and reconciliation plan in chat before writing.

Do not create empty generic chapters.

### 5. Generate

Read [references/output-contract.md](references/output-contract.md).

1. Patch a valid draft instead of rewriting it wholesale.
2. Preserve accurate wording, IDs, links, and unrelated user edits.
3. Translate actions into direct procedures for the supported interface.
4. Translate assertions into observable pass criteria.
5. Add setup and cleanup only when evidence establishes them.
6. Keep scenario bodies appropriate for the least technical person who can operate the interface.
7. Do **not** add chapter Sources tables, verification indexes, reconciliation summaries, evidence
   statuses, or inline gap warnings to the playbook.
8. Put environment-specific prerequisites in Environment handoff or scenario Setup, using normal
   tester language.

### 6. Verify

When `verify` or `run_tests` is true:

1. Follow the repository's own installation, test, and start commands.
2. Prefer focused tests while iterating, then run the relevant complete suite when practical.
3. Exercise the supported UI, API client, CLI, device, job trigger, or integration when safe.
4. Record commands, environment, date, results, and relevant test names in the agent report.
5. Separate infrastructure failures from product failures.
6. Never mutate production without explicit approval.

When verification is false, keep unpublished status as `SOURCED` or leave the scenario out until
evidence is enough. Do not run tests merely to improve an internal status.

### 7. Validate, snapshot, and report

Run:

```bash
python3 <skill-dir>/scripts/validate_playbook.py "<output_dir>"
```

Fix every structural error. Review warnings.

After validation succeeds, write evidence state:

```bash
python3 <skill-dir>/scripts/inventory_playbook.py "<output_dir>" \
  --code-repo "<code_repo>" \
  --docs-path "<docs_path>" \
  --write-state
```

Confirm:

- Every planned scenario appears exactly once in the results template.
- Every internal link resolves.
- The playbook Markdown contains no Sources tables, verification indexes, reconciliation history,
  evidence statuses, or `NEEDS VERIFICATION` markers.
- State contains no credentials, customer data, access links, or absolute user-specific source
  paths.
- Generated prose contains no em dashes or semicolons.

Report to the user in chat: files touched, scenario count, verification performed, reused or
changed scenarios, unresolved items still needing a user decision, and cleanup obligations. Do not
append that report to the playbook.

## Handle unknown projects

If surface or framework detection returns `unknown`:

1. Search test commands, CI, contracts, drivers, fixtures, and naming conventions.
2. Identify actions followed by observable assertions.
3. Fall back to source, docs, and safe observation.
4. Keep low-confidence journeys out of the published playbook until evidence is enough, or ask the
   user which ones to include with Environment handoff caveats.
5. Explain in chat what evidence would raise confidence.

Do not reject a product because it uses an unfamiliar language or framework.
