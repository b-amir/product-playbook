# Portable collaboration state

## Contents

1. State shape
2. Stable source identity
3. Full reconciliation
4. Scoped contributions
5. Concurrent work
6. Safety rules

## State shape

Keep authoring state beside the canonical playbook:

```text
.product-playbook-state.json
```

Keep this file out of the tester-facing playbook map. It may be versioned with the canonical
playbook so another contributor can safely continue the work. Never split it into per-source or
per-scenario files.

## Stable source identity

Choose short source IDs based on product responsibility, not repository branding or a machine
location. Examples include `web`, `api`, `mobile`, `docs`, and `contracts`.

State may contain:

- the portable `"managed_by": "product-playbook"` format identifier;
- source ID and kind;
- source-relative evidence paths;
- content hashes;
- source revision;
- scenario body hashes.

State must not contain:

- absolute paths;
- checkout locations;
- credentials, tokens, access links, or customer data;
- developer, organization, or machine identifiers;
- installation paths or repository-specific tool URLs;
- unresolved claims presented as evidence;
- verification status, authoring timestamps, issues, or history.

## Full reconciliation

Use a full reconciliation only when all sources required by every published scenario are accessible.
Require current ledger evidence for every scenario. A full reconciliation may add, update, merge,
split, or remove scenarios.

Run a coverage scan even when all existing scenario evidence is unchanged.

## Scoped contributions

Use a contribution when only some sources are accessible. Pass every accessible source ID through
`--scope`.

A contribution may:

- add a scenario proved by scoped evidence;
- update a scenario when scoped evidence supports every changed published detail;
- add a source to a cross-component scenario;
- preserve prior evidence from unavailable sources.

A contribution must not:

- remove a scenario;
- modify an out-of-scope scenario;
- treat an unavailable source as stale;
- claim complete product coverage;
- replace a canonical draft with a separately generated playbook.

If a changed shared contract may affect inaccessible scenarios, report them as possible follow-up
work without editing or downgrading them.

## Concurrent work

Read `state_digest` from `.product-playbook-state.json` before editing. Pass it back as
`--base-state-digest` when writing state. If it changed, reload the current canonical draft and
reapply the focused contribution.

Use ordinary version-control branches and review workflows when teams work simultaneously. The
skill prepares focused files and detects stale state. It does not silently merge divergent drafts,
commit, push, or publish changes without explicit user authorization.

The digest covers the full state document, including every source and scenario entry. Resolve a
genuine same-scenario conflict using current evidence from every involved source.

## Legacy migration

Run `inventory_playbook.py "<output_dir>" --migrate-state` when an older playbook contains
`.product-playbook/`. Migration consolidates the legacy manifest, source entries, and scenario
entries into `.product-playbook-state.json`. It removes only recognized legacy JSON files and
refuses cleanup when the directory contains anything else.

## Safety rules

- Resolve every evidence path inside its declared source root.
- Reject absolute paths and `..` traversal.
- Exclude the canonical output directory from source fingerprints.
- Preserve unavailable source and scenario state during contributions.
- Remove stale state entries only during a full reconciliation.
- Validate Markdown first, write state second, then validate both together.
