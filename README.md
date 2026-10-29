<p align="center">
  <img src="https://raw.githubusercontent.com/b-amir/product-playbook/main/assets/readme/hero.svg" width="100%" alt="Product Playbook turns product evidence into plain steps like sign in and select Continue, with optional Export PDF">
</p>

<p align="center">
  <a href="https://skills.sh/b-amir/product-playbook"><img src="https://img.shields.io/badge/skills.sh-product--playbook-000000" alt="Install from skills.sh"></a>
  <a href="https://agentskills.io/"><img src="https://img.shields.io/badge/Agent%20Skills-compatible-111111" alt="Agent Skills compatible"></a>
  <a href="https://github.com/b-amir/product-playbook/actions/workflows/validate.yml"><img src="https://github.com/b-amir/product-playbook/actions/workflows/validate.yml/badge.svg" alt="Validate skill"></a>
  <img src="https://img.shields.io/badge/python-3.9%2B-3776AB?logo=python&logoColor=white" alt="Python 3.9+">
  <a href="https://github.com/b-amir/product-playbook/blob/main/LICENSE"><img src="https://img.shields.io/github/license/b-amir/product-playbook" alt="MIT license"></a>
</p>

<p align="center">
  <strong>Turn tests, contracts, Swagger, docs, and source into a playbook a non-technical tester can run.</strong><br>
  A portable <a href="https://agentskills.io/">Agent Skill</a> for QA, product, support, and operations.
</p>

## Install

```bash
npx skills add b-amir/product-playbook
```

Then ask your agent:

```text
Use $product-playbook to inspect this workspace.
```

Works with Cursor, Claude Code, Codex, OpenCode, Gemini CLI, and GitHub Copilot via the [`skills` CLI](https://github.com/vercel-labs/skills). Helpers need Python 3.9+ (stdlib only).

## What you get

<p align="center">
  <img src="https://raw.githubusercontent.com/b-amir/product-playbook/main/assets/readme/workflow.svg" width="100%" alt="Folder tree under docs/ with playbook/ and sibling playbook-findings/">
</p>

- **`playbook/`** — scenario chapters, results template, and `.product-playbook-state.json`.
- **`playbook-tests/`** — optional runnable tests with the same scenario IDs, plus one `playbook-tests.json` for targets and safety tags.
- **`playbook-findings/`** — optional Agent-check notes (drift, defects), kept as a sibling folder.

## How a run feels

Every agent follows the same protocol: **Intake → Plan → Write**, then optional Export or Agent-check.

1. Intake — discover the product, show What I found as a table, then lettered choices in the same message (no polls).
2. **Plan** — Keep / Update / Add table. No Markdown writes until you approve.
3. **Write** — tester-facing chapters + one `.product-playbook-state.json`, plus runnable tests if you opted in.
4. **Opt-in** — PDF/HTML export, or Agent-check findings in `playbook-findings/`.

Full rules: [`SKILL.md`](SKILL.md) · [`references/run-protocol.md`](references/run-protocol.md)

## What it is for

Any product surface: web, API, CLI, worker, RAG, mobile, SDK, monorepo, or multi-repo. Partial team access is supported — contributors update what they can reach and preserve the rest.

It does **not** invent button labels or endpoints. Claims come from observation, tests, contracts, source, then docs.

## Canonical details

- Testers see finished procedures only — no Sources tables, verification history, or authoring gaps.
- State holds portable fingerprints for the next reconcile. Nothing else.
- PDF/HTML are derived on request ([`references/export.md`](references/export.md)).

## Bootstrap (scripts)

```bash
python3 scripts/bootstrap_playbook.py
```

Or with explicit sources:

```bash
python3 scripts/bootstrap_playbook.py \
  --source "web=./apps/web" \
  --source "api=./services/api" \
  --docs-source "docs=./docs" \
  --output-dir "./docs/playbook"
```

After analysis, render or reconcile:

```bash
python3 scripts/render_playbook.py ./plan.json ./docs/playbook
python3 scripts/validate_playbook.py ./docs/playbook
```

Examples: [`examples.md`](examples.md) · Output contract: [`references/output-contract.md`](references/output-contract.md)

## Runnable tests (opt-in)

Answer **B** to "Also generate runnable tests?" at Intake. Each evidence-backed scenario gets a test in the product's own framework (else Playwright for web, Playwright API or pytest for HTTP, shell for CLI). Steps the evidence cannot back stay manual-only.

```bash
python3 scripts/playbook_tests.py run ./docs/playbook-tests --target local
python3 scripts/playbook_tests.py run ./docs/playbook-tests --target prod   # smoke/safe only
```

- Targets live in `playbook-tests.json`. Credentials are env var names only, never values.
- Tags `smoke` / `safe` / `destructive`. Prod skips `destructive` unless you pass `--allow-destructive`.
- Acceptance examples (`EX-9.1-9` Given/When/Then) import with `import-acceptance` and trace to a scenario, a test, and a result.
- Scenarios can declare `requires` (s3, sqs, llm-real) and targets `provides`; unmet needs are
  reported as E (Blocked, environment), never as failures.
- The run prints a short P/F/B/E/U/N table you can paste into a ticket. Manual results merge in with `--manual ID=P`.
- **U** (Not built yet) comes from a readiness check: scenario `readiness` markers missing from the
  code (`--source app=../app`), a `[not-built]` test skip, or a ticket state outside `tickets.ready_states`.
- Optional ticket pinning: `--ticket ABC-123`, `--ticket-file ticket.md`, `--ticket-state Test`. Each
  run records commits, target and time in `playbook-runs/` (local).
- `retest` diffs against the last run (fixed / still failing / newly broken) and reruns neighbouring
  scenarios; `changed` maps new commits to scenarios and suggests what to rerun without running it.

New here? Start with [`QUICKSTART.md`](QUICKSTART.md). Details: [`references/runs.md`](references/runs.md).

Rules: [`references/tests.md`](references/tests.md)

## Contributions, drift, and Agent-check

Scoped inventory when only some sources are available:

```bash
python3 scripts/inventory_playbook.py ./docs/playbook \
  --source "api=./services/api" \
  --run-scope contribution \
  --scope api \
  --check-state
```

CI drift (exit `1` when evidence moved):

```bash
python3 scripts/inventory_playbook.py ./docs/playbook \
  --source "api=./services/api" \
  --check-state --drift \
  --tests-dir ./docs/playbook-tests   # optional: also flag tests whose evidence moved
```

Drop-in workflow: [`examples/github-action-validate-playbook.yml`](examples/github-action-validate-playbook.yml).  
Agent-check rules: [`references/agent-check.md`](references/agent-check.md).  
Collaboration state: [`references/collaboration-state.md`](references/collaboration-state.md).

## Companions

| Skill | Use when |
| --- | --- |
| [`product-playbook-audit`](companions/product-playbook-audit/SKILL.md) | Read-only audit / drift |
| [`product-playbook-export`](companions/product-playbook-export/SKILL.md) | PDF or HTML only |

## Develop

```bash
python3 -m unittest discover -s tests -v
```

Eval fixture: [`evals/`](evals/) (its reference tests run against the fixture API in the suite). Schemas: [`schemas/`](schemas/).

## License

MIT. Issues: [github.com/b-amir/product-playbook/issues](https://github.com/b-amir/product-playbook/issues).
