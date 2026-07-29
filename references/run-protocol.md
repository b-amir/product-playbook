# Run protocol

Every agent and harness follows the same phases. Do not invent alternate workflows.
Paraphrase only inside the required slots.

## Phases (mandatory order)

```text
Task progress:
- [ ] 1. Intake   (discover + confirm; no writes)
- [ ] 2. Plan     (coverage decisions; no Markdown/state writes)
- [ ] 3. Write    (Markdown patch/create → validate → state)
- [ ] 4a. Export      (only if user explicitly asks)
- [ ] 4b. Agent-check (only if user explicitly asks)
```

Hard stops:

1. After Intake polls until the user answers.
2. After Plan until the user Approves, Adjusts, or chooses Audit-only.
3. After Write, stop unless they ask for Export or Agent-check.

Audit-only skips Write. Agent-check-only may skip Write when a playbook already exists.
Export and Agent-check never run by default.

## Confirmations across harnesses

Prefer the richest structured choice UI the current agent offers (polls, multi-select,
AskUserQuestion, Codex/Claude/OpenCode choice widgets, and similar).

If no structured UI exists, present the same options as a compact numbered or lettered list
and ask the user to reply with their selections in one message. Never ask the five intake
polls as five separate turns when one bundled round is enough.

## Phase 1 — Intake Card (required slots)

Fill every slot. Lead with product shape. Do not dump freeform discovery essays.

1. **Product shape** — surfaces detected and confidence (mixed is allowed)
2. **Roots** — in-scope local roots and sanitized remotes
3. **Roles** — assumed role per root (product, docs, frontend, API, worker, RAG, …)
4. **Evidence hits** — counts or short lists: contracts, tests, docs, runtime URLs, prior work
5. **Prior playbook** — path and whether portable state exists
6. **Proposed canonical path** — proposal only until confirmed
7. **Polls** — see [intake.md](intake.md)

On second and later runs, open with a **Reconcile Summary** before the full card when state
exists:

- state digest
- changed sources
- impacted vs reusable vs preserved-out-of-scope counts
- contribution vs full recommendation

Skip re-asking the destination when state and draft agree, unless the user chose Create or
there is a path conflict.

## Phase 2 — Plan

Present a table before any write:

| Decision | Scenario IDs | Notes |
| --- | --- | --- |
| Keep / Update / Split / Merge / Remove / Add / Needs evidence | … | … |

Include contribution boundary and approximate tester time. Wait for Approve / Adjust /
Audit-only.

**Propose-only:** when the user wants a review gate, write the validated plan JSON (and
optional patch notes) to a path they choose. Do not write playbook Markdown or state until
they approve.

## Phase 3 — Write

1. Render or patch Markdown per [output-contract.md](output-contract.md)
2. `validate_playbook.py`
3. `inventory_playbook.py --write-state` with ledger
4. `validate_playbook.py --require-state`
5. Emit the End Report

## End Report (fixed shape every time)

```text
## End report
- Mode: create | reconcile | audit | agent-check | export
- Playbook: <output_dir>
- Files touched: …
- Scenarios: total N · added · updated · removed · preserved OOS
- Sources: accessible … · preserved …
- Verification: none | tests | live smoke | agent-check (summary)
- Findings file: none | <path>
- Unresolved decisions: …
- Cleanup: temporary checkouts, etc.
```

Never put End Report content into tester-facing Markdown or into
`.product-playbook-state.json`.

## Playbook folder purity

Inside `<output_dir>` publish only:

- `README.md`, numbered chapters, `results-template.md`
- `.product-playbook-state.json` (machine fingerprints only)

Optional derived `playbook.pdf` / `playbook.html` only on explicit ask.
Agent-check findings go to the sibling folder documented in [agent-check.md](agent-check.md).
