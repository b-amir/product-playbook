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

## Contribution decisions (chat only — never in the playbook)

```text
| Decision | IDs | Notes |
| Keep | BILL-02, BILL-03 | Fingerprints unchanged |
| Update | ACC-01 | Label Send → Send magic link |
| Add | ACC-04 | New invite journey in api tests |
| Preserved OOS | PAY-01–PAY-06 | payments source not in scope |
```

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
