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

## Scenario → runnable test (opt-in)

Same ID in three places: the procedure (`ACC-01` in the chapter), the test, the result row.

```python
# playbook-tests/test_playbook_accounts.py  (evidence: openapi.yaml, tests/test_accounts.py)
BASE_URL = os.environ["PLAYBOOK_BASE_URL"]

class Accounts(unittest.TestCase):
    def test_ACC_01_create_account(self):
        status, body = post_accounts({"name": "Playbook Tester"})
        self.assertEqual(status, 201)
        self.assertTrue(body.get("id"))
```

```ts
// Web UI, Playwright: labels come from the playbook / existing tests, never invented
test("AUTH-01 request a magic link", async ({ page }) => {
  await page.goto("/login");
  await page.getByRole("button", { name: "Send magic link" }).click();
  await expect(page.getByText("Check your email")).toBeVisible();
});
```

Config entry (`playbook-tests/playbook-tests.json`):

```json
"ACC-01": {
  "tags": ["smoke", "destructive"],
  "test": "test_playbook_accounts.py",
  "run": ["{python}", "-m", "unittest", "test_playbook_accounts.Accounts.test_ACC_01_create_account"],
  "acceptance": ["EX-1.1-1"],
  "evidence": [{"source_id": "api", "path": "openapi.yaml"}]
},
"ACC-07": {"manual_only": true, "reason": "Needs an emailed link; no test inbox in evidence"}
```

Run summary to paste into a ticket:

```markdown
**Playbook run** · target `dev` (dev) · 2026-10-29 14:47 (UTC+03:00)

P 1 · F 0 · B 0 · N 1

| ID | Result | Run | Acceptance | Notes |
| --- | --- | --- | --- | --- |
| ACC-01 | P | Auto | EX-1.1-1 |  |
| ACC-07 | N | Manual |  | manual only |

Acceptance: 1/1 examples mapped
```

Full working fixture: [`evals/reference/`](evals/reference/).

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
- Runnable tests: docs/playbook-tests · auto 9 · manual-only 3 · run on local: P 9 F 0 B 0 N 3
- Findings file: none
- Unresolved decisions: none
- Cleanup: none
```
