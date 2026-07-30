# Intake confirmation

One confirmation round after discovery. No writes until the user answers.

Goal: show the findings table in chat, then ask lettered questions in the **same**
message. The user almost never types free text.

## Hard rule: no polls for Intake

Do **not** use polls, AskQuestion, multi-select widgets, or any choice UI for Intake.

Those widgets hide or detach the findings table, so users get asked about facts they
cannot see.

Intake is always one chat message:

1. **What I found** table
2. Short disclaimer: `Correct me if I'm wrong.`
3. Lettered questions with recommended answers in the same text

Reserve polls for later steps that do **not** need the user to confirm a table
(for example Plan approve, or after-Plan export / agent-check picks).

## Hard rule: verbatim bootstrap output

Consistency comes from the script, not from the model.

1. Run `bootstrap_playbook.py` with explicit `--source` / `--docs-source` when possible.
2. Print `intake.intake_message` **verbatim**. Do not rewrite the table. Do not invent rows.
3. Preserve every blank line, `###` heading, and list item. Never collapse choices onto one line.
4. Same sources and same tree → same Intake message.
5. If two chats disagree, compare the **Scope** row and the sources that were passed in.

Do not freehand discovery into the table. Agents that paraphrase will drift.

Never show count-only jargon such as `product: 2 linked` or `1 warning(s)`.
If nearby repos or mocks exist, the script lists real paths. If none exist, those rows
are omitted entirely.

## Consistency checklist

| Cause of drift | Fix |
| --- | --- |
| Different cwd or `--source` roots | Pass the same sources every time |
| One chat finds `unified-docs`, another only `frontend/` | Include every intended root explicitly |
| Model rewrote the table | Print `intake_message` verbatim |
| Model crushed options onto one line | Preserve blank lines and list breaks from the script |
| Weak auth/viewport false positives | Trust the script markers after bootstrap |

Show Scope in the table so the user can see what was scanned.

## What I found

Always include Scope through Permission checks. Add nearby-repo and mock rows **only**
when the script found concrete paths.

| Section | Plain language |
| --- | --- |
| Scope | Which source IDs and paths were scanned |
| Product | What kind of product this looks like |
| Folders | What we will use, and what each one is for |
| Existing playbook | Where a playbook already lives, if any |
| Save location | Where the playbook would go |
| Product roles | Named roles/tiers from enums or seeds (Administrator, Manager, …). Never permission actions, chat roles, or agent-tool personas |
| Width-sensitive screens | Places phone and desktop may differ |
| Permission checks | Places access may change by role |
| Nearby repos (not in Folders yet) | Nested/linked repos with paths — omit row when empty |
| Mocks / fixtures / generated | Concrete warning paths — omit row when empty |

Required chat shape (prefer `intake.intake_message` from bootstrap):

```markdown
## What I found

| Item | Value |
| --- | --- |
| Scope | product=/path/to/repo |
| Product | web app + API |
| Folders | web → apps/web (web app); api → services/api (API) |
| Existing playbook | docs/playbook |
| Save location | docs/playbook |
| Product roles | Admin, Member |
| Width-sensitive screens | none found |
| Permission checks | none found |

Correct me if I'm wrong.

## Choose

Reply with letters only.
Recommended: `A A A`

### 1. What should I do?

- **A.** Update the existing playbook ← recommended
- **B.** Create a new playbook
- **C.** Review only (no file changes)
- **D.** Run checks against the live product

### 2. Which folders should I use?

- **A.** All folders listed above ← recommended
- **Z.** Add another folder or Git URL

### 3. Where should the playbook live?

- **A.** Use the existing playbook path ← recommended
- **B.** Use the suggested path: docs/playbook
- **C.** Somewhere else

---

Reply like: `A A A`

Or just: `recommended`
```

When nearby repos or mock warnings exist, the script adds those table rows and matching
questions. Do not invent them by hand.

Do not ask a separate “does this look right?” question. The disclaimer covers that.
If something in the table is wrong, the user corrects it in the same reply.

## Reply rules

- One letter per question, in order.
- Multi-select may use several letters for that question, like `BC`.
- Free text only after a choice that needs it (custom path, corrections).
- `recommended` means accept every recommended choice.
- Corrections to the table may appear in the same reply as the letters.

## Questions

Ask only needed decisions. Mark exactly one recommended choice per single-select question.

### 1. What should I do?

- A. Update the existing playbook `(recommended when a playbook exists)`
- B. Create a new playbook `(recommended when no playbook exists)`
- C. Review only (no file changes)
- D. Run checks against the live product

### 2. Which folders should I use?

- A. All folders listed above `(recommended)`
- B / C / … one letter per listed folder for a custom subset
- Z. Add another folder or Git URL `(then paste the path after your letters)`

### 3. Where should the playbook live?

- A. Use the existing playbook path `(recommended when one exists)`
- B. Use the suggested path `(recommended when creating)`
- C. Somewhere else `(then paste the path after your letters)`

### Optional (same message, only when needed)

Nearby repos listed in the table:

- A. Include none `(recommended)`
- B. Include some `(then list names after your letters)`

Mocks / fixtures / generated listed in the table:

- A. Leave them out `(recommended)`
- B. Include some anyway `(then list names after your letters)`

## When polls are allowed

Use harness polls only when the user is **not** confirming a findings table:

| Step | Polls OK? |
| --- | --- |
| Intake (What I found + choices) | No. Text only. |
| Plan approve / adjust / review only | Yes |
| After Plan (stop / smoke / agent-check / export) | Yes |

For those later steps, prefer polls when available. Otherwise use a short lettered menu.
Mark the recommended answer.

## Plan gate

- A. Approve the plan `(recommended)`
- B. Adjust the plan `(then write the changes)`
- C. Review only (do not write files)

## After Plan approval

- A. Stop here `(recommended)`
- B. Quick smoke check while writing
- C. Full product check → findings folder
- D. Export PDF
- E. Export HTML

## First-run vs later runs

| Situation | Emphasis |
| --- | --- |
| No playbook | Full What I found + questions 1–3 |
| Playbook + state | Short what changed + light What I found + question 1 at minimum |
| Playbook, no state | Full review before reuse |
| Partial access | Say what you can reach. Do not delete unseen sections |
| Docs repo present | Prefer that docs folder as the save location |

## Anti-patterns

- Using polls / AskQuestion for Intake
- Paraphrasing or inventing Intake table rows
- Showing `N linked` / `N warning(s)` instead of real paths
- Collapsing lettered choices onto one line
- Asking about findings the user cannot see next to the question
- Hiding the recommended answer
- Forcing free-text paths when a discovered path exists
- Asking one Intake question per turn
- Writing before answers
- Surfacing digests, hashes, fingerprints, or session IDs to the user
- Creating a second playbook for the same product because another repo joined
- Re-asking Create when Update is clearly the right default
