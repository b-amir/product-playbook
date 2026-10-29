# Runnable tests

Opt-in companion output: executable tests that share the playbook's scenario IDs.
The playbook stays the human procedure. Tests are a second, machine-run view of the
same scenarios. Never generate them unless the user picked it at Intake or Plan.

## Contents

1. Where tests live
2. Choosing the stack
3. Evidence gate
4. Config: targets, credentials, tags
5. Acceptance examples
6. Running and reporting
7. Drift
8. Write-phase checklist
9. Environment capabilities ([environments.md](environments.md))

## Where tests live

Sibling of the playbook, never inside it:

```text
<playbook-parent>/
├── playbook/                 # Markdown + .product-playbook-state.json only
├── playbook-tests/
│   ├── playbook-tests.json   # targets, tags, scenario → test → evidence, acceptance
│   └── <generated test files>
└── playbook-findings/        # Agent-check only
```

If the product already keeps e2e tests in a known folder and the user wants them there, put the
test files there and point `workdir` / `test` at them. `playbook-tests.json` still lives in
`playbook-tests/`. Schema: [../schemas/playbook-tests.schema.json](../schemas/playbook-tests.schema.json).

## Choosing the stack

1. **Product's own framework first.** If discovery found Playwright, Cypress, pytest, Jest/Vitest
   with supertest, Go test, etc., write tests in that framework and its conventions. Reuse its
   fixtures, base-URL config, and auth helpers.
2. Otherwise by surface:
   - Web UI → Playwright Test (TypeScript). One `test()` per scenario, title starts with the ID
     (`test('ACC-01 create account', …)`), `baseURL` from `PLAYBOOK_BASE_URL`.
   - HTTP API → Playwright `request` when Node is already in the repo, else pytest (or stdlib
     `unittest` + `urllib` when pytest is not present) reading `PLAYBOOK_BASE_URL`.
   - CLI / worker → a POSIX shell script per scenario that exits non-zero on failure, using a
     disposable temp dir. Observe workers through their supported completion signal only.
3. Never add global installs. Local `npm i -D` / venv `pip install` only when the user agreed
   and the product does not already provide the runner.

Name test functions after the ID (`test_ACC_01_…`, `ACC-01 …`) so a grep for the ID finds the
procedure, the test, and the result row.

## Evidence gate

Automate a step only with the same evidence order as the playbook:
observation > passing test > test source > contract + source > docs.

- Endpoints, methods, status codes, fields: from contracts, routes, or existing tests.
- Selectors: prefer roles + exact visible labels already in the playbook (`getByRole('button',
  { name: 'Create account' })`), or `data-testid` values that exist in source. Never invent
  selectors, ids, or CSS paths.
- Test data: from fixtures, seeds, or the playbook's safe test-data table.
- A scenario whose key step or assertion cannot be backed stays **manual-only** with a
  one-line `reason` in the config. Do not write a placeholder test that always passes or skips.
- Record every file the test relied on under `evidence` (`source_id` + source-relative path).

## Config: targets, credentials, tags

`playbook-tests.json` declares targets once:

```json
"targets": {
  "local": {"kind": "local", "base_url": "http://127.0.0.1:3000"},
  "dev":   {"kind": "dev",   "base_url_env": "PLAYBOOK_DEV_URL"},
  "prod":  {"kind": "prod",  "base_url_env": "PLAYBOOK_PROD_URL"}
},
"credentials_env": ["PLAYBOOK_USER", "PLAYBOOK_PASSWORD"]
```

- Any one-off URL: `run --base-url <url>` (kind `custom`).
- Credentials only as env var **names**. Tests read `os.environ` / `process.env`. Never write a
  value into the config, test files, `.env` files, the playbook, or the chat.
- Prod URLs only via `base_url_env`. The checker rejects literal prod URLs, `user:pass@` URLs,
  and secret-looking keys with literal values.

Tags per automated scenario (at least one):

| Tag | Meaning |
| --- | --- |
| `smoke` | Part of the smoke path |
| `safe` | Read-only or fully self-cleaning. Safe on shared environments |
| `destructive` | Creates, changes, or deletes shared data, sends messages, or charges money |

Environment capabilities: a scenario may declare `requires: ["s3", "sqs"]` and each target
`provides: [...]`. The runner never runs a scenario whose requirements the target lacks; it
records **E** (Blocked, environment). See [environments.md](environments.md).

`safe` and `destructive` are exclusive. On a `prod` target the runner selects only `smoke`/`safe`
scenarios and always skips `destructive` unless `--allow-destructive` is passed (ask the user
first, every time).

## Acceptance examples

When the user provides acceptance examples (Given/When/Then with IDs such as `EX-9.1-9`):

```bash
python3 <skill-dir>/scripts/playbook_tests.py import-acceptance <tests_dir> <examples.md>
```

Then map each example to the scenario(s) that cover it with the scenario's `acceptance` list.
The run summary shows mapped, failing, and unmapped examples, so each example traces to a
procedure (ID), a test (same ID), and a result. Keep these IDs out of the published playbook
(traceability tables are forbidden there). An unmapped example is a Plan item
(Add / Needs evidence), not a silent gap.

## Running and reporting

```bash
python3 <skill-dir>/scripts/playbook_tests.py check <tests_dir> --playbook <output_dir>
python3 <skill-dir>/scripts/playbook_tests.py run <tests_dir> --target local
python3 <skill-dir>/scripts/playbook_tests.py run <tests_dir> --target prod          # smoke/safe only
python3 <skill-dir>/scripts/playbook_tests.py run <tests_dir> --base-url https://pr-42.example \
  --tags smoke --manual "ACC-04=P" --manual "ACC-05=B:no device" --output run.md
```

The runner sets `PLAYBOOK_BASE_URL`, `PLAYBOOK_TARGET`, `PLAYBOOK_TARGET_KIND`, runs each
scenario's `run` argv (`{python}` = current interpreter), and prints a pasteable summary:

```markdown
**Playbook run** · target `dev` (dev) · 2026-10-29 14:47 (UTC+03:00)

P 2 · F 1 · B 0 · E 0 · U 0 · N 1

| ID | Result | Run | Acceptance | Notes |
| --- | --- | --- | --- | --- |
| ACC-01 | P | Auto | EX-1.1-1 |  |
| ACC-02 | F | Auto | EX-1.1-2 | AssertionError: 500 != 400 |
| ACC-03 | N | Manual |  | manual only |

Acceptance: 2/2 examples mapped · failing EX-1.1-2
```

Exit codes: `0` no failures, `1` a scenario failed, `2` config/target error. Exit 0 with every
test skipped, pytest exit 5, timeouts, or a missing runner are **B** (Blocked), never P.
Unmet `requires`, or a skip whose output carries the `[env]` marker, is **E** (Blocked,
environment): the environment cannot run it, which says nothing about the code. F means only a
code or test failure. `--provide s3,sqs` adds capabilities for one run (an emulator you just
started). A readiness gap or a `[not-built]` skip is **U** (Not built yet). Manual results merge with `--manual ID=P|F|B|E|U|N[:note]`, so one summary covers mixed runs. The
playbook's `results-template.md` has a matching **Run** column (Manual / Auto).

Ticket-pinned runs (`--ticket`, `--ticket-file`, `--ticket-state`), commit pinning (`--source`),
run history, `retest`, `history`, and `changed` are in [runs.md](runs.md). Optional config:
`tickets.pattern`, `tickets.ready_states`, `history_dir`, and per scenario `tickets` and
`readiness` (see `schemas/playbook-tests.schema.json`).

Run summaries are run output. Paste them into the ticket or save them next to the tests. Never
into the playbook folder.

## Drift

After writing or reviewing tests, record fingerprints:

```bash
python3 <skill-dir>/scripts/playbook_tests.py fingerprint <tests_dir> --source "SOURCE_ID=<root>"
```

Later, either check alone or fold into the playbook drift check:

```bash
python3 <skill-dir>/scripts/playbook_tests.py drift <tests_dir> --source "SOURCE_ID=<root>"
python3 <skill-dir>/scripts/inventory_playbook.py <output_dir> --source "SOURCE_ID=<root>" \
  --check-state --drift --tests-dir <tests_dir>
```

`stale_tests` lists scenario IDs whose test file or any evidence file changed or disappeared.
Treat them like impacted scenarios: re-check evidence, update procedure and test together,
re-run, then re-fingerprint. Sources not passed are reported as `unchecked_sources`.

## Write-phase checklist

1. Plan carries `automated_tests.enabled` and per-scenario `automation` (`tags`, or
   `manual_only` + `reason`, optional `acceptance`).
2. Write playbook Markdown first and validate it.
3. Generate tests for automated scenarios only, using the detected framework.
4. Write `playbook-tests.json`, then `fingerprint`.
5. `validate_playbook.py <output_dir> --tests-dir <tests_dir>`.
6. Run against `local` (or the target the user named) when the product can be started safely.
   Report the summary. A failing generated test is either a product defect (keep the test,
   report it) or a wrong test (fix it from evidence). Never weaken an assertion to go green.
