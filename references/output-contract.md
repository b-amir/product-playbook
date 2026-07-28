# Playbook output contract

## Contents

1. Folder shape
2. Hub requirements
3. Chapter requirements
4. Scenario requirements
5. Results-template requirements
6. Surface-specific requirements
7. Reconciliation state
8. Writing rules
9. Forbidden in published Markdown

## Folder shape

Create:

```text
<output_dir>/
├── README.md
├── 01-<journey>.md
├── 02-<journey>.md
├── NN-quality-sweep.md
├── results-template.md
└── .product-playbook-state.json
```

Add or omit journey chapters according to evidence. Number chapters in the order a user encounters
them. Create the state file only after validating the Markdown.

The destination directory is chosen by the skill destination policy. Prefer one playbook tree per
product. Do not publish separate per-repo playbooks for the same product unless the user explicitly
wants different audiences (for example an API-only operator book). Even then, name folders by
audience, not by repository brand.


## Hub requirements

Include:

- One-paragraph purpose and audience
- Test-pass table with pass name, use case, scope, and estimated time
- Playbook map linking every chapter
- Actors, identities, tools, and safe test-data table derived from real interfaces and entities
- Numbered setup checklist
- Environment-owner handoff
- Confirmed interface reference for routes, endpoints, commands, events, jobs, or mobile screens
- Scenario field definitions
- Pass, Fail, Blocked, and N/A result definitions
- Failure-evidence checklist
- Blocker, Major, Minor, and Cosmetic severity guide with product-relevant examples
- Ordered smoke path using scenario IDs
- Full-pass order
- Sign-off rules

Estimate time from scenario count and complexity. Mark the estimate as approximate.

Do **not** include a verification index, reconciliation summary, evidence-status table, or links to
authoring history.

## Chapter requirements

Include:

1. A one-line introduction
2. A scenario list table with ID, scenario, and persona
3. Every scenario in the same order
4. A chapter checklist code block containing every scenario ID
5. A link to the next chapter or the results template

Use stable uppercase prefixes derived from chapter names. Do not reuse an ID. For non-browser
products, adapt the quality sweep to the product's supported client, runtime, resilience, and
failure surfaces.

Do **not** end chapters with a Sources section, status table, conflict log, or verification note.

## Scenario requirements

Use:

```markdown
## XX-01: Observable user outcome

**Goal**

State the user outcome.

**Who**

Name the persona or account type.

**Setup**

Include only when needed.

**Steps**

1. Use exact visible labels, endpoints, commands, options, fields, or event names in **bold** or
   `code`.

**Expected**

- State observable results grounded in assertions or observation.

**Record**

Include only when useful.

**Cleanup**

Include only when state changes.

**Note**

Explain optional or environment-dependent subchecks in plain tester language.
```

Require Goal, Who, Steps, and Expected. Ensure every expected result has a corresponding action or
explicit setup. Ensure every action that changes state has cleanup or an environment-owner
instruction.

For browser scenarios, bold exact visible labels. For API, CLI, service, and mobile scenarios, use
the exact interface syntax defined below.

Never publish inline gap warnings such as `⚠️ NEEDS VERIFICATION`. If a label or outcome is not
established, resolve it from evidence or omit that step until it is.

## Results-template requirements

Include:

- Run details
- Browser, API client, runtime, device, or environment coverage as applicable
- Accounts, actors, and identities used without credentials or access links
- Test data, starting state, and cleanup state
- P, F, B, and N legend
- One results table per chapter mirroring every scenario ID
- Defects with severity and evidence
- Blocked and N/A details
- Cleanup tracking
- Counts by result
- Recommendation and sign-off

Explain that a scenario passes only when all applicable required outcomes pass. Allow named
optional subchecks to be recorded as N/A or Blocked in Notes without hiding a required failure.

## Surface-specific requirements

### Browser frontend

- Use exact visible labels and observable page outcomes.
- Include responsive, keyboard, zoom, loading, empty, error, and not-found checks only when
  supported by evidence or when the environment owner includes them in scope.

### API or backend

- State the exact HTTP method and path.
- State required headers, identity, fields, and safe fixture data without secrets.
- Derive expected status codes and response properties from tests or executable contracts.
- Include validation, permissions, pagination, idempotency, concurrency, errors, and retries only
  when the product exposes and supports those behaviors.
- Prefer an approved API client or test console. Do not require a non-technical reader to write
  code.

### CLI

- Copy the command, subcommand, options, arguments, exit code, stdout, stderr, and output paths
  exactly.
- Use safe placeholders and a disposable working directory.

### Service, worker, event, or webhook

- Identify the supported trigger and observable completion signal.
- Document retry or failure handling only when a tester can trigger and observe it safely.
- Do not turn internal implementation details into unsupported manual procedures.

### Mobile

- Record device, operating system, orientation, permission state, connectivity, and deep-link
  prerequisites when relevant.

### Full-stack

- Lead with the user journey.
- Add API or service observations only when they establish an otherwise invisible result or isolate
  a failure.

## Reconciliation state

Write `.product-playbook-state.json` after successful validation by running
`inventory_playbook.py --write-state`. Keep it machine-readable and free of secrets or absolute
user-specific paths.

Use the state only to narrow future fact-checking. Never present it as product behavior, never list
it in the playbook map, and never ask testers to open it.

## Writing rules

- Address the least technical reader who can operate the supported product interface.
- Use short direct sentences.
- Use numbered actions and observable outcomes.
- Use product and interface terminology only when verified.
- Use exact visible labels in bold and exact technical interface tokens in code formatting.
- Avoid implementation language in scenario bodies.
- Avoid security analysis unless the user journey itself requires a security-related action.
- Do not use em dashes or semicolons in prose. Preserve them only when they are part of exact
  interface tokens, commands, code, or cited source text.
- Never include credentials, tokens, private links, real customer data, or production secrets.
- Write finished procedures. Do not expose authoring uncertainty, evidence quality, or update
  history in the playbook.

## Forbidden in published Markdown

Do not include any of the following in README, chapters, or the results template:

- Verification index
- Reconciliation summary or change history
- Chapter Sources / source-map tables
- Evidence statuses such as `VERIFIED`, `SOURCED`, or `NEEDS VERIFICATION`
- Inline markers such as `⚠️ NEEDS VERIFICATION`
- Conflict or gap columns
- Links that exist only to explain how the playbook was authored
- Mentions of automated test file paths unless the tester must run those commands as part of the
  product procedure
