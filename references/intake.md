# Intake polls

Bundle these into one confirmation round after the Intake Card. Use the harness choice UI
when available; otherwise a single numbered list.

## Poll 1 — What should this run do?

1. Create a new playbook
2. Continue / reconcile an existing playbook
3. Audit only (no Markdown or state writes)
4. Agent-check only (exercise the product; write findings; do not edit the playbook unless asked)

## Poll 2 — Which roots are in scope?

Multi-select discovered local roots and sanitized remotes. Offer “add another path or Git URL.”

## Poll 3 — Where is the canonical playbook?

1. Each discovered playbook candidate
2. The mechanical default (for example `<source>/docs/playbook`) when applicable
3. Custom path (user supplies it)

On reconcile, default to the existing canonical path when state and draft agree.

## Poll 4 — Roles and product boundary

1. Accept assumed roles
2. Edit the role map (user corrects)
3. Exclude one or more roots from this product

## Poll 5 — After Plan, what else?

Asked after Plan approval (or immediately in Agent-check-only mode):

1. Nothing else this run
2. Read-only smoke / live interface check as part of Write or Agent-check
3. Full Agent-check (tests + live interfaces when safe) → findings sibling folder
4. Export PDF
5. Export HTML

## First-run vs later runs

| Situation | Intake emphasis |
| --- | --- |
| No playbook | Full card + polls 1–4; propose destination |
| Playbook + state | Reconcile Summary first; light card; poll 1; expand roots if newly available |
| Playbook, no state | Treat as first reconciliation; full factual audit before reuse |
| Partial team access | Contribution scope; never remove OOS scenarios |
| Unified docs repo | Prefer that docs root as canonical destination |

## Anti-patterns

- Asking polls one-at-a-time across many turns without need
- Writing before poll answers
- Re-running Create when Continue is clearly appropriate without asking
- Forking a second playbook for the same product because another repo joined
