# Agent-check and findings

Optional mode. Run only when the user asks to verify, smoke-test, agent-check, or find drift.
Do everything the agent can safely do: read-only and mutating checks in approved environments,
repository test commands, live Swagger/OpenAPI, UI, CLI, jobs, and devices.

## Output location

Write findings to a **sibling** folder of the playbook — never inside the playbook directory:

```text
<playbook-parent>/
├── playbook/                 # tester-facing Markdown + state JSON only
└── playbook-findings/        # agent/developer findings (this mode)
    └── YYYY-MM-DDTHHMMSS.md
```

If the playbook path is `/docs/playbook`, findings go to `/docs/playbook-findings/`.
Create the findings directory as needed. Never place findings beside chapter Markdown inside
`playbook/`. Never merge findings into `.product-playbook-state.json`.

## Safety matrix

| Class | Allowed by default? | Requires |
| --- | --- | --- |
| Read-only UI walk / GET-like API / `--help` CLI | Yes, when URLs or commands are known | Discovered or user-supplied base URL |
| Staging smoke that creates disposable data | Only with user approval | Cleanup plan |
| Run repository unit/integration/e2e commands | Yes when commands are discovered and non-destructive to shared prod | Prefer focused then broader suites |
| Hit live Swagger / OpenAPI “try it” against staging | Yes when address is non-production or user confirms | Compare contract vs behavior |
| Production reads that cannot leak customer data | Only with explicit approval | Redaction |
| Production writes / real customer data / secret exfiltration | Never | — |

Never mutate production without an explicit user order in this run.
Never store credentials, tokens, or customer payloads in findings files.

## What to exercise (do everything possible)

1. **Playbook smoke path** — execute smoke-ordered scenarios against the live interface when reachable.
2. **Contract live check** — for discovered OpenAPI/Swagger/AsyncAPI servers, confirm critical operations respond as documented (auth permitting).
3. **Repository tests** — run discovered test commands from bootstrap (`pytest`, `npm test`, Playwright, etc.), focused first, then broader when practical.
4. **UI / CLI / jobs / mobile** — use browser, HTTP client, CLI, or device tools the harness provides.
5. **Cross-check** — compare observed labels, status codes, and errors to published playbook steps.

Record pass/fail per scenario ID when applicable. Note environment, revision, and commands run.

## Findings file shape

```markdown
# Playbook findings — <ISO timestamp>

## Environment
- Playbook: <output_dir>
- Bases / commands: …
- Git revisions: …

## Summary
- Scenarios checked: …
- Defects: N · Drift: N · Blocked: N

## Defects and drift
### F-01 — short title
- Severity: Blocker | Major | Minor | Cosmetic
- Scenario: ACC-01 (if any)
- Expected: …
- Observed: …
- Evidence: …

## Test commands run
- `…` → exit code …

## Suggested playbook updates
- Update ACC-01 step 3 label (requires Plan → Write; do not edit yet unless user approved)
```

## After Agent-check

- Summarize in chat using the End Report (`Findings file: <path>`).
- Do **not** edit the playbook unless the user approves a Plan that incorporates findings.
- Findings are hypotheses plus observations. They are not automatic publication truth.

## Relationship to Verify during Write

During a normal Write, optional verification may run tests or a light smoke and stay in chat /
the temporary ledger only. Persistent findings files are reserved for Agent-check (or when the
user explicitly asks to save findings).
