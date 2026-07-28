---
name: product-playbook
description: Create, reconcile, audit, or incrementally improve evidence-backed manual testing and product-usage playbooks from local directories, local repositories, remote Git repositories, tests, contracts, source, documentation, and optional live verification. Use for frontend, API, backend, full-stack, CLI, service, worker, integration, and mobile products, including monorepos, multi-repository products, partial team contributions, manual testing documentation, product playbooks, and playbook reconciliation. Never invent interface terms or behavior. Keep published output tester-facing and all source locations runtime-supplied.
---

# Product Playbook

Create one canonical tester-facing Markdown playbook from any number of runtime evidence sources.
Treat source locations, product structure, team boundaries, and the output destination as discovered
inputs. Never embed organization names, developer names, machine paths, repository names, or
product-specific assumptions in this skill.

Keep all portable fingerprints in the single file
`<output_dir>/.product-playbook-state.json`. Never create a state directory or per-source and
per-scenario files. Do not persist verification status, authoring timestamps, issues, history, or
unresolved notes there. Never publish source maps or authoring metadata in tester-facing Markdown.

## Start from the available inputs

Require at least one evidence source. Accept local directories and Git repository URLs:

```text
SOURCE_ID=PATH_OR_URL
```

Use stable, product-neutral source IDs such as `web`, `api`, `mobile`, `docs`, or `contracts`.
Locations are runtime-only. Store only source IDs, source-relative paths, content hashes, and
revisions in collaboration state.

Accept:

- `source`: One or more code, test, contract, or executable product roots
- `docs_source`: Zero or more documentation roots
- `output_dir`: Canonical playbook directory
- `draft_path`: Explicit existing playbook
- `run_scope`: `auto`, `full`, `contribution`, or `audit`
- `scope`: Source IDs accessible to this run
- `product_surface`: One or more surfaces, or `auto`
- `test_framework`: One or more frameworks, or `auto`
- `verify` or `run_tests`: Whether to execute tests or operate a supported interface

Do not require a separate docs source. Discover documentation inside supplied sources. Treat absent
documentation as a discovery result, not a reason to delay analysis.

## Bootstrap in one command

Run:

```bash
python3 <skill-dir>/scripts/bootstrap_playbook.py \
  --source "product=<path-or-url>"
```

Repeat `--source` and `--docs-source` as needed. Add `--source-ref "SOURCE_ID=REF"` for a branch,
tag, or commit. Add `--workspace-dir` when the caller chooses where remote read-only checkouts live.

The bootstrap report provides:

- acquired runtime roots and cleanup obligations;
- all detected surfaces and confidence, without collapsing mixed products;
- components, frameworks, tests, commands, contracts, interfaces, and instruction files;
- unclassified evidence and recommended next probes;
- existing draft candidates and the canonical destination decision;
- the suggested run scope and next action.

Read repository instruction files before interpreting evidence. Do not modify evidence sources.
Clean temporary remote checkouts after the run.

## Choose the canonical output

Resolve the destination in this order:

1. Use explicit `output_dir`.
2. Use explicit `draft_path`, or its parent when it is a file.
3. Reuse exactly one confidently discovered playbook.
4. With one local code source and no separate docs source, use `<source>/docs/playbook`.
5. Otherwise complete discovery and ask for the destination before writing.

Ask which draft is authoritative when several credible drafts exist. Never merge divergent drafts
automatically. Reuse the same canonical output as new sources or teams contribute later. Do not
fork the playbook merely because evidence lives in another repository.

The output may live inside an evidence repository, in a separate repository, or in any explicit
directory. Exclude it from source discovery and fingerprints.

## Choose the run scope

Use:

- `full` when all intended product components are accessible;
- `contribution` when only a subset of sources is accessible;
- `audit` when the user asks for assessment without changes;
- `auto` to inspect component coverage and existing state before choosing.

Do not infer completeness from source count. One monorepo may contain the whole product, while
several repositories may still represent only one team's accessible scope.

During a contribution:

- preserve scenarios outside the accessible scope;
- add or update only scenarios supported by accessible sources;
- never remove an inaccessible scenario;
- never downgrade evidence merely because its source is unavailable;
- preserve cross-component scenarios unless scoped evidence proves a change;
- refuse to change an out-of-scope scenario without new scoped evidence.

Allow scenario removal only during a full reconciliation or when the user explicitly authorizes a
different canonical scope. Read
[references/collaboration-state.md](references/collaboration-state.md) before a contribution run.

## Apply the evidence rules

Use this priority for each factual claim:

1. Successful current observation through the supported interface
2. Passing current end-to-end or integration test
3. Current test source that was not executed
4. Executable contract and application source
5. Technical documentation
6. Existing playbook prose

Copy visible labels, endpoints, methods, fields, commands, options, events, roles, statuses, and
observable outcomes exactly. Trace helpers, fixtures, mocks, contracts, access checks, and cleanup
behavior that affect the user-visible result.

Use statuses only in the current chat and temporary evidence ledger:

- `VERIFIED`: The complete scenario passed during this run.
- `SOURCED`: Every published detail traces to current evidence.
- `UNRESOLVED`: A required detail is missing, conflicting, failing, or inferred.

Do not publish or persist these statuses. Resolve `UNRESOLVED` content, omit it, or ask the user.
Treat previous verification as non-current unless the scenario passes again during this run.

## Run the workflow

### 1. Discover

Use the bootstrap report. Read
[references/framework-discovery.md](references/framework-discovery.md) for the detected surfaces.
If detection is unknown or low confidence, inspect the recommended probes rather than rejecting the
project.

### 2. Inventory and check state

Skip only when no draft exists. Read
[references/draft-reconciliation.md](references/draft-reconciliation.md), then run:

```bash
python3 <skill-dir>/scripts/inventory_playbook.py "<output_dir>" \
  --source "SOURCE_ID=<acquired-local-root>" \
  --run-scope contribution \
  --scope "SOURCE_ID" \
  --check-state
```

Capture `state_digest` before editing. Use `reusable_scenarios`, `impacted_scenarios`,
`changed_sources`, and `preserved_out_of_scope` to narrow analysis. Never use state to skip coverage
discovery, changed shared contracts, authentication, permissions, fixtures, routing, or whole-output
validation.

### 3. Analyze

For every new or impacted journey, record in an internal JSON evidence ledger:

```json
{
  "scenarios": {
    "ACC-01": {
      "status": "SOURCED",
      "sources": [
        {
          "source_id": "api",
          "path": "tests/accounts_test.py"
        }
      ]
    }
  }
}
```

Use source-relative paths only. For cross-component journeys, cite every source needed to establish
the published steps and outcomes.

### 4. Reconcile or plan

Classify existing scenarios as Keep, Update, Split, Merge, Remove, Add, or Needs more evidence.
Preserve an ID when the user outcome remains materially the same. Explain removals and ID changes
in chat, not in the playbook.

Group scenarios by real journey. Adapt the quality sweep to detected surfaces. Present the planned
coverage and contribution boundary before writing.

### 5. Generate

Read [references/output-contract.md](references/output-contract.md).

- For a new playbook, render the evidence-backed JSON plan:

  ```bash
  python3 <skill-dir>/scripts/render_playbook.py "<plan.json>" "<output_dir>"
  ```

- Patch a valid draft instead of rewriting it.
- Preserve accurate wording, IDs, links, and unrelated edits.
- Translate actions into direct procedures and assertions into observable pass criteria.
- Include setup and cleanup only when evidence establishes them.
- Keep scenario bodies appropriate for the least technical supported operator.
- Never publish Sources tables, evidence status, reconciliation summaries, or gap markers.

### 6. Verify

When verification is requested, follow the source repository's own commands. Prefer focused tests
while iterating, then the relevant complete suite when practical. Exercise the supported UI, API
client, CLI, device, job trigger, or integration only when safe. Never mutate production without
explicit approval.

Record verification details in chat and the internal ledger. Do not add them to tester-facing
Markdown.

### 7. Validate and write portable state

Validate the Markdown:

```bash
python3 <skill-dir>/scripts/validate_playbook.py "<output_dir>"
```

Write collaboration state only after Markdown validation succeeds:

```bash
python3 <skill-dir>/scripts/inventory_playbook.py "<output_dir>" \
  --source "SOURCE_ID=<acquired-local-root>" \
  --run-scope contribution \
  --scope "SOURCE_ID" \
  --evidence-ledger "<ledger.json>" \
  --base-state-digest "<digest-read-before-editing>" \
  --write-state
```

Omit `--base-state-digest` only when no prior state exists. Use `--run-scope full` only when every
published scenario has current ledger evidence.

If an older playbook contains `.product-playbook/`, consolidate it before continuing:

```bash
python3 <skill-dir>/scripts/inventory_playbook.py "<output_dir>" --migrate-state
```

Migration accepts only the legacy manifest and its JSON source and scenario entries. It refuses to
remove an unrecognized file.

Then validate state and Markdown together:

```bash
python3 <skill-dir>/scripts/validate_playbook.py "<output_dir>" --require-state
```

If the state digest changed after analysis, reload the canonical draft and reconcile the focused
patch again. Do not overwrite newer work.

Report files touched, scenario count, accessible and preserved sources, verification performed,
changed scenarios, unresolved decisions, and cleanup obligations in chat.
