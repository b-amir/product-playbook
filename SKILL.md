---
name: product-playbook
description: Inspect product workspaces and create, reconcile, audit, or incrementally improve evidence-backed manual testing and product-usage playbooks from local or remote repositories, tests, contracts, source, documentation, and optional live verification. Use for first-run repository intake and for frontend, API, backend, full-stack, CLI, service, worker, RAG, integration, SDK, helper-library, tooling, data, contract, extension, and mobile products, including monorepos, multi-repository products, partial team contributions, manual testing documentation, product playbooks, and playbook reconciliation. Never invent interface terms or behavior. Keep published output tester-facing and all source locations runtime-supplied.
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
The state writer adds `"managed_by": "product-playbook"` so contributors can identify the owning
tool without storing a machine path or repository-specific URL.

## Start with an intake when intent is unclear

When the user invokes the skill without naming an action, source, or destination, run the bootstrap
from the current working directory with no arguments:

```bash
python3 <skill-dir>/scripts/bootstrap_playbook.py
```

This is an inspect-and-confirm pass. Do not write playbook files, run tests, operate a live
interface, clone an unprovided remote, or update state yet. Present:

- every discovered local repository root and sanitized Git remote;
- the assumed role of each source, including product, docs, frontend, API, RAG, worker,
  integration, SDK, helper library, contract, extension, data, and tooling roles;
- linked or nested repository candidates;
- contracts, cached or generated contract copies, runtime-address candidates, API behavior,
  tests, commands, documentation, and repository instructions;
- existing playbooks, portable state, QA artifacts, scenario catalogs, reports, and other prior
  work;
- the proposed canonical output and whether to continue, reconcile, or create.

Then ask the user to confirm:

1. Are these the correct local and remote addresses for the in-scope product repositories?
2. Which repository is the canonical documentation repository?
3. Are the assumed repository roles and intended product boundary correct?
4. Should existing work continue at the discovered canonical path?
5. Do they want an audit, an edit or reconciliation, a new playbook, or verification?

Bundle obvious confirmations into one concise intake rather than asking them serially. Stop before
writing until the user confirms or corrects material assumptions. A mechanical default such as
`<source>/docs/playbook` is only a proposal during this intake.

## Start from the available inputs

Require at least one evidence source. Accept local directories and Git repository URLs:

```text
SOURCE_ID=PATH_OR_URL
```

Use stable, product-neutral source IDs such as `web`, `api`, `rag`, `worker`, `sdk`, `shared`,
`integration`, `docs`, or `contracts`. A source ID describes responsibility, not repository
technology or branding. Locations and Git remotes are runtime-only. Store only the portable
manager identifier, source IDs, source-relative paths, content hashes, and revisions in
collaboration state.

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

Do not assume one repository equals one product component. Inspect workspace manifests, nested Git
repositories, submodules, packages, services, workers, jobs, RAG and retrieval code, integrations,
SDKs, shared libraries, extensions, data pipelines, contract-only roots, and tooling. Ask which
ones belong to the same tester-facing product when the boundary is ambiguous.

## Bootstrap in one command

Run:

```bash
python3 <skill-dir>/scripts/bootstrap_playbook.py \
  --source "product=<path-or-url>" \
  --intent auto
```

Repeat `--source` and `--docs-source` as needed. Add `--source-ref "SOURCE_ID=REF"` for a branch,
tag, or commit. Add `--workspace-dir` when the caller chooses where remote read-only checkouts live.

The bootstrap report provides:

- acquired runtime roots and cleanup obligations;
- local Git roots, branches, sanitized remotes, and linked repository candidates;
- all detected surfaces and confidence, without collapsing mixed products;
- components, frameworks, tests, commands, documentation, interfaces, and instruction files;
- OpenAPI, Swagger, AsyncAPI, GraphQL, protobuf, RAML, generated API schemas, frontend contract
  copies, contract server addresses, runtime URLs, and API-address environment variables;
- backend routes, handlers, authorization, schema, integration, webhook, RAG, and retrieval
  behavior candidates;
- existing playbooks, state, QA plans, UAT material, scenario catalogs, reports, API-client
  collections, and other prior work;
- unclassified evidence and recommended next probes;
- existing draft candidates and the canonical destination decision;
- structured assumptions and confirmation questions when `--intent auto` is used;
- the suggested run scope and next action.

Read repository instruction files before interpreting evidence. Do not modify evidence sources.
Clean temporary remote checkouts after the run.

Repository instructions may declare a checkout to be a mock, fixture, generated copy, partial
export, or wrapper. Treat that as a scope warning. Do not promote fixture tests or absent-source
documentation into product truth. When a contract, catalog, mock, and implementation disagree,
report the conflict and ask which product boundary is intended.

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

During an auto-intake, confirm even a unique draft or default destination before writing. Ask
whether discovered state and prior work should continue on the same path. If a product-wide
playbook exists in a documentation repository, do not create a per-repository fork.

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

Use contract copies and generated clients carefully. A frontend `openapi.json`, generated schema,
or cached client proves what that consumer was generated against, not automatically what the
current backend deploys. Compare revisions, contract metadata, paths, operations, schemas, server
addresses, and backend behavior. Record conflicts in chat and do not silently choose one copy.

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

#### Optional single-file PDF or HTML export

Markdown is the default and only automatic output. Produce a single combined PDF,
or a single HTML file, only when the user explicitly asks for one. Never run this
path for a normal creation, edit, reconciliation, or audit.

First make sure the Markdown is valid, then export:

```bash
python3 <skill-dir>/scripts/validate_playbook.py "<output_dir>"

# PDF (default): writes <output_dir>/playbook.pdf and removes the intermediate HTML.
python3 <skill-dir>/scripts/export_playbook.py "<output_dir>" [--output PATH] [--force]

# HTML only: writes <output_dir>/playbook.html and leaves it in place.
python3 <skill-dir>/scripts/export_playbook.py "<output_dir>" --format html [--output PATH] [--force]
```

`export_playbook.py` reads only `README.md`, numbered chapters, and
`results-template.md`. It ignores `.product-playbook-state.json` and any non-
Markdown file, so collaboration state never reaches testers. The exporter itself
needs only the standard library.

`--format pdf` builds the print-ready HTML in a private location, then prints it
to PDF using the first available converter: Google Chrome or Chromium headless,
`wkhtmltopdf`, or `pandoc`. The intermediate HTML is deleted, leaving only
`playbook.pdf`. If no converter is found, the export fails with a clear message
instead of leaving an HTML file behind. Do not install a converter, and do not
assume one is present.

`--format html` writes a single self-contained `playbook.html` and stops there.
Use it only when the user asks for HTML specifically. Do not print it to PDF in
this mode and do not delete it: they asked for the HTML.

Treat `playbook.pdf` and `playbook.html` as regenerable derived artifacts. They
are not part of the canonical folder shape, are never written by the default
workflow, and do not need to be reconciled on later edits. Delete or regenerate
them whenever the Markdown changes.

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
