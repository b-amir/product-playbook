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

1. After Intake choices until the user answers (letters or structured picks).
2. After Plan until the user picks Approve, Adjust, or Review only.
3. After Write, stop unless they ask for Export or Agent-check.

Audit-only skips Write. Agent-check-only may skip Write when a playbook already exists.
Export and Agent-check never run by default.

## Confirmations across harnesses

Make answering easy. Prefer picking over typing.

1. Prefer the richest structured choice UI the current agent offers (polls, multi-select,
   AskUserQuestion, Codex/Claude/OpenCode choice widgets, and similar).
2. Pre-select or clearly mark the recommended answers.
3. If no structured UI exists, show one lettered menu. Ask for option letters only.
4. Accept `recommended` as a full accept of every recommended choice.
5. Allow free text only after the user picks an option that needs it.

Never split Intake into many turns when one round is enough.
Never ask the user to write sentences when a letter will do.

## Phase 1 — Intake Card (required slots)

Fill every slot that has evidence. Lead with product shape. Do not dump freeform discovery essays.
Do not show digests, fingerprints, hashes, or session IDs to the user.

1. **Product** — what kind of product this looks like (mixed is allowed)
2. **Folders and repos** — what we will use, and what each one is for
3. **Existing playbook** — path if one already exists
4. **Suggested save location** — proposal only until confirmed
5. **What I found** — print `findings_chat_block` as a markdown table in chat before any choice UI
6. **Questions** — lettered choices with a recommended reply. See [intake.md](intake.md)

Hard rule: never open polls until the formatted findings table is visible in chat.
Keep question 0 short (`Do the findings above look right?`). Never dump the table into the
poll prompt.

Ask the user to reply with letters only, like `A A A`, or `recommended`.
Free text only if they pick a choice that needs it.

On second and later runs, open with a short **What changed** summary when state exists:

- which sources changed
- how many scenarios look impacted vs reusable vs left alone
- whether this should be a partial update or a full pass

Keep machine digests out of that summary. Use them only inside scripts.

## Phase 2 — Plan

Present a table before any write:

| Decision | Scenario IDs | Notes |
| --- | --- | --- |
| Keep / Update / Split / Merge / Remove / Add / Needs evidence | … | … |

When viewport-sensitivity evidence exists for a scenario, put `viewport: yes` and a short evidence
hint in Notes (for example `matchMedia in permission gate`). Omit that flag when there is no
viewport fork for the journey. Do not mark every browser scenario viewport-sensitive.

Include contribution boundary and approximate tester time.
Ask for a pick-only Plan gate:

- A. Approve the plan `(recommended)`
- B. Adjust the plan
- C. Review only (do not write files)

Accept `A` or `recommended`.

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
