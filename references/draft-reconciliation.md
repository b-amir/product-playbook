# Draft reconciliation and incremental updates

## Contents

1. Selection rules
2. Trust model
3. First reconciliation
4. Incremental reconciliation
5. Scenario decisions
6. Token-efficiency rules
7. Safety rules

## Selection rules

Use this order:

1. Use an explicit `output_dir` when provided.
2. Use an explicit `draft_path` when provided.
3. Use the only confidently detected playbook candidate under the supplied sources.
4. Ask the user when multiple candidates exist. Never merge drafts automatically.
5. With exactly one local code source and no separate docs source, create
   `<local-source>/docs/playbook` when no draft exists.
6. With remote-only inputs, several code sources, a separate docs source, or an otherwise ambiguous
   destination, ask for `output_dir` before writing.

Never hardcode product names or documentation-repo brand names. The same `output_dir` must be reused
when additional evidence roots join later so the playbook reconciles instead of forking.


## Trust model

Treat a draft as:

- A useful inventory of journeys, personas, wording, IDs, and cleanup knowledge
- A hypothesis about current behavior
- A non-authoritative source that may contain stale labels, routes, roles, or expected results

Do not treat draft prose as proof of current behavior.

## First reconciliation

When no `.product-playbook-state.json` exists:

1. Run `inventory_playbook.py --check-state` with stable source IDs.
2. Preserve the draft until the audit is complete.
3. Match every draft scenario to current tests, contracts, source, docs, or observation.
4. Classify each scenario as Keep, Update, Split, Merge, Remove, Add, or Needs more evidence.
5. Preserve an existing ID when the user outcome remains materially the same.
6. Resolve labels and outcomes before writing. Update state after validation.
7. Run a coverage scan for journeys absent from the draft.

A first reconciliation can reuse prose, but it cannot skip factual auditing.

## Incremental reconciliation

Use incremental reuse only when:

- The portable state file exists and its schema is supported
- The draft scenario set still matches the state
- Relevant source fingerprints are unchanged for reused scenarios

Always:

1. Re-run product discovery.
2. Check state and repository fingerprints.
3. Re-audit impacted scenarios.
4. Scan changed roots for new or removed journeys.
5. Recheck shared authentication, permissions, routing, fixtures, contracts, and global
   configuration when they changed.
6. Revalidate the whole output.

Do not interpret an unchanged cited file as proof when a shared helper or contract changed.

## Scenario decisions

Use:

| Decision | Meaning |
| -------- | ------- |
| Keep | Evidence and wording remain current |
| Update | Same outcome, but steps, labels, setup, or results changed |
| Split | One draft scenario now represents multiple independent outcomes |
| Merge | Multiple draft scenarios now describe one outcome |
| Remove | The product no longer exposes the journey |
| Add | Current evidence reveals a missing journey |
| Needs more evidence | Evidence is missing, conflicting, or failing |

Explain removals and ID changes in the agent chat report. Do not publish a reconciliation summary in
the playbook. Do not silently erase a scenario without telling the user.

## Token-efficiency rules

Reduce repeated work by:

- Reading the compact draft inventory before full chapter prose
- Loading only impacted scenario bodies during a safe incremental update
- Reusing unchanged wording verbatim
- Preserving stable IDs and results rows
- Using repository diffs and fingerprints to narrow the audit

Do not save tokens by:

- Trusting draft expected results
- Skipping coverage discovery
- Ignoring shared helpers, fixtures, permissions, or contracts
- Publishing unresolved labels for the tester to figure out
- Marking old execution evidence as current `VERIFIED` in state

## Safety rules

- Make a focused patch rather than rewriting the directory when reconciliation is safe.
- Preserve unrelated user edits.
- Do not delete superseded scenarios until the chat report explains the replacement.
- Write `.product-playbook-state.json` only after the playbook validates.
- Never store credentials, access links, customer data, or absolute user-specific paths in state.
- Keep the published Markdown tester-facing. Put authoring uncertainty only in chat or state.
- During a contribution, preserve inaccessible scenarios and reject unsupported edits.
