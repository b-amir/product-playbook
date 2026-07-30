# Intake confirmation

One confirmation round after discovery. No writes until the user answers.

Goal: the user should almost never type free text. They pick options.

## Hard rule: show findings before any choice UI

Never ask “look right?” until the user can see a readable **What I found** block.

Required order every time:

1. Print the full **What I found** block in the chat message first.
   Use a markdown table or short bullets. Keep it easy to scan.
2. Then open polls / AskQuestion / lettered menu.
3. Keep question 0 short. Point at the chat block above.
   Do **not** paste the full findings into the poll prompt.

Why: many poll UIs flatten newlines and bold the whole prompt into one hard-to-read line.

Question 0 prompt shape (poll-safe, one or two short lines):

```text
Do the findings above look right?
```

Optional tiny hint only if the chat may be scrolled away:

```text
Do the findings above look right? (product, folders, playbook)
```

Forbidden:

- Dumping Product / Folders / Playbook / Roles into the poll question text
- Asking question 0 with no **What I found** block in chat
- Opening polls first and promising to show findings later
- Saying “Presenting the Intake Card” without printing the findings block

## How to ask (required)

1. Prefer the harness structured choice UI when it exists (polls, multi-select,
   AskUserQuestion, Codex / Claude / OpenCode choice widgets).
2. Pre-select or mark the recommended answers in that UI.
3. If no structured UI exists, show one compact lettered menu and ask for a
   single reply of letters only.

Never split Intake into many turns when one round is enough.

Do not ask about digests, fingerprints, state hashes, session IDs, portable
locators, or other machine metadata.

## Reply rules for the user

Tell them exactly how to answer:

```text
Reply with option letters only, like: A A A
Recommended: A A A
```

Rules:

- One letter per question, in order.
- Multi-select questions may use several letters for that question, like `BC`.
- Free text is allowed only after choosing an option that says so
  (for example B = Corrections, or C = Somewhere else).
- If they reply with only `A A A` or `recommended`, use every recommended choice.

## What I found

Print this block in chat before any poll. Show only what discovery found. Skip empty sections.

| Section | Plain language |
| --- | --- |
| Product | What kind of product this looks like |
| Folders | What we will use, and what each one is for |
| Existing playbook | Where a playbook already lives, if any |
| Save location | Where the playbook would go |
| Product roles | Account types we think exist |
| Width-sensitive screens | Places phone and desktop may differ |
| Permission checks | Places access may change by role |
| Related folders | Nested or linked repos we noticed |
| Caution | Things that look like mocks or generated copies |

Minimum shape in chat (formatted, scannable):

```markdown
## What I found

| Item | Value |
| --- | --- |
| Product | web app + API |
| Folders | web → apps/web (web app); api → services/api (API) |
| Existing playbook | docs/playbook |
| Save location | docs/playbook |
| Product roles | Admin, Member |
| Width-sensitive screens | none found |
| Permission checks | none found |

These are working assumptions from the repo, not the final playbook.
Review the table, then answer the questions.
```

Then ask question 0 with a short poll-safe prompt.

### 0. Do the findings above look right?

Prompt (keep short — do not paste the table here):

```text
Do the findings above look right?
```

Choices:

- A. Yes, continue with these findings `(recommended)`
- B. No, I will correct them after submitting

If they pick B, they may write short corrections after the letters.
Do not make them rewrite the whole card.

## Questions

Ask only needed decisions. Bundle them in one round. Mark exactly one recommended
choice per single-select question.

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

### Optional (same round, only when needed)

Related folders:

- A. Include none `(recommended)`
- B. Include some `(then list names after your letters)`

Caution items:

- A. Leave them out `(recommended)`
- B. Include some anyway `(then list names after your letters)`

## Fallback menu shape

When there is no structured UI, render exactly this pattern:

```text
## What I found
...short bullets...

## Choose (reply with letters only)
Recommended: A A A

0. Do the findings above look right?
   A. Yes, continue with these findings (recommended)
   B. No, I will correct them after submitting

1. What should I do?
   A. Update the existing playbook (recommended)
   B. Create a new playbook
   C. Review only (no file changes)
   D. Run checks against the live product

2. Which folders should I use?
   A. All folders listed above (recommended)
   Z. Add another folder or Git URL

3. Where should the playbook live?
   A. Use the existing playbook path (recommended)
   B. Use the suggested path: docs/playbook
   C. Somewhere else

Reply like: A A A
Or: recommended
```

Adapt letters and recommendations to what discovery found. Keep the reply line.

## After Plan approval

Same pick-only rule. Mark a recommendation.

- A. Stop here `(recommended)`
- B. Quick smoke check while writing
- C. Full product check → findings folder
- D. Export PDF
- E. Export HTML

Multi-select is allowed here when the harness supports it. In text fallback, accept
several letters such as `C D`.

## Plan gate

Also pick-only:

- A. Approve the plan `(recommended)`
- B. Adjust the plan `(then write the changes)`
- C. Review only (do not write files)

## First-run vs later runs

| Situation | Emphasis |
| --- | --- |
| No playbook | Full What I found + questions 0–3 |
| Playbook + state | Short what changed + light What I found + question 1 at minimum |
| Playbook, no state | Full review before reuse |
| Partial access | Say what you can reach. Do not delete unseen sections |
| Docs repo present | Prefer that docs folder as the save location |

## Anti-patterns

- Dumping findings into the poll prompt so they become one unreadable bold line
- Asking “look right?” before findings are visible as a formatted chat table
- Opening polls first and promising to show findings later
- Asking the user to write sentences when a letter would do
- Hiding the recommended answer
- Forcing free-text paths when a discovered path exists
- Asking one question per turn
- Writing before answers
- Surfacing digests, hashes, fingerprints, or session IDs
- Creating a second playbook for the same product because another repo joined
- Re-asking Create when Update is clearly the right default
