# Intake confirmation

One confirmation round after discovery. No writes until the user answers.

Goal: the user should almost never type free text. They pick options.

## Hard rule: show findings before any choice UI

Never ask “Does this look right?” until the user can see **What I found**.

Required order every time:

1. Print the full **What I found** block in the chat message (bullets, not jargon).
2. Then open polls / AskQuestion / lettered menu.
3. Question 0 must also include a short findings recap inside the question text,
   because some harnesses show only the poll card and hide the chat above it.

If the poll UI would appear alone, put the findings in the first question prompt.
Do not open a choice UI with an empty or generic “look right?” question.

Forbidden:

- Asking question 0 with no findings visible in chat and no findings in the prompt
- Opening polls first and promising to show findings later
- Saying “Presenting the Intake Card” without the card contents

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

Minimum shape:

```text
## What I found

Product: …
Folders:
- name → path (what it is)
Existing playbook: … or none
Save location: …
Product roles: … or none found
Width-sensitive screens: … or none found
Permission checks: … or none found

These are working assumptions from the repo, not the final playbook.
```

Then ask question 0. The question prompt must repeat a short version of the same facts.

### 0. Do these findings look right?

Prompt must include the findings, for example:

```text
Do these findings look right?
Product: web app + API
Folders: web, api, docs
Playbook: docs/playbook
Roles: Admin, Member
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

0. Do these findings look right?
   Product: …
   Folders: …
   Playbook: …
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

- Asking “look right?” before findings are visible in chat and in the question prompt
- Opening polls first and promising to show findings later
- Asking the user to write sentences when a letter would do
- Hiding the recommended answer
- Forcing free-text paths when a discovered path exists
- Asking one question per turn
- Writing before answers
- Surfacing digests, hashes, fingerprints, or session IDs
- Creating a second playbook for the same product because another repo joined
- Re-asking Create when Update is clearly the right default
