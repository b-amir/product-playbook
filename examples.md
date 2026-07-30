# Examples

Golden translations and reports. Copy the shape; never copy fake product labels into a real run.

## Playwright assertion → manual step

**Evidence (test):**

```ts
await page.getByRole("button", { name: "Send magic link" }).click();
await expect(page.getByText("Check your email")).toBeVisible();
```

**Playbook:**

```markdown
## AUTH-01: Request a magic link

**Goal**

Receive confirmation that a magic link email was requested.

**Who**

Signed-out visitor with an approved test inbox.

**Steps**

1. Open the sign-in page.
2. Enter the approved test email.
3. Select **Send magic link**.

**Expected**

- The page shows **Check your email**.
```

## OpenAPI operation → API scenario

**Evidence:** `POST /v1/accounts` returns `201` with `{ "id": "…" }` when `name` is set.

**Playbook:**

```markdown
## ACC-01: Create an account

**Goal**

Create an account through the public API.

**Who**

API tester with a staging credential.

**Steps**

1. `POST /v1/accounts` with JSON body field `name` set to an approved disposable value.
2. Record the returned `id`.

**Expected**

- Response status is `201`.
- Response body includes an `id` value.
```

## Viewport-sensitive browser scenario

**Evidence:** permission chrome uses `useMediaQuery` / `md:` layout forks. Desktop shows **Continue**.
Narrow layout hides the action behind a different gate.

**Plan Notes:** `viewport: yes · useMediaQuery in permission chrome`

**Playbook:**

```markdown
## AUTH-03: Reach the protected action

**Goal**

Open the protected action when the approved role is signed in.

**Who**

Signed-in member with the approved role.

**Steps**

1. Open the protected page while signed in.
2. Confirm whether **Continue** is available.

**Expected**

- The page allows the approved role to continue.

**Across viewports**

- Narrow (~375px): the approved role can still reach **Continue** through the narrow chrome.
- Wide (~1280px): the approved role can select **Continue**.
- Must match: allow or deny outcome for the same role across both widths.
- Watch for: missing action, alternate menu-only path, or a different permission message.
```

Do not add **Across viewports** to scenarios without viewport-fork evidence.

## Contribution decisions (chat only — never in the playbook)

```text
| Decision | IDs | Notes |
| Keep | BILL-02, BILL-03 | Fingerprints unchanged |
| Update | ACC-01 | Label Send → Send magic link |
| Add | ACC-04 | New invite journey in api tests |
| Preserved OOS | PAY-01–PAY-06 | payments source not in scope |
```

## Intake: What I found (chat only — no polls)

Print `intake.intake_message` from bootstrap verbatim. Preserve blank lines. Example shape:

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

Do not open a poll UI for this step. Do not rewrite the table by hand.
Omit nearby-repo and mock rows when empty. Never invent count-only jargon.

## Forbidden in published Markdown

Do not publish:

```markdown
## Sources
| Scenario | File |
| ACC-01 | tests/accounts_test.py |

⚠️ NEEDS VERIFICATION
```

Keep provenance in the temporary ledger and chat End Report only.

## End report shape

```text
## End report
- Mode: reconcile
- Playbook: docs/playbook
- Files touched: 01-account.md, .product-playbook-state.json
- Scenarios: total 12 · added 1 · updated 1 · removed 0 · preserved OOS 6
- Sources: accessible api, docs · preserved payments
- Verification: pytest tests/accounts -q
- Findings file: none
- Unresolved decisions: none
- Cleanup: none
```
