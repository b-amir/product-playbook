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
- **`playbook-findings/`** — optional Agent-check notes (drift, defects), kept as a sibling folder.

## How a run feels

Every agent follows the same protocol: **Intake → Plan → Write**, then optional Export or Agent-check.

1. **Intake** — discover product shape, roots, remotes, contracts, and prior playbooks. One confirmation round (structured choices when the agent has them).
2. **Plan** — Keep / Update / Add table. No Markdown writes until you approve.
3. **Write** — tester-facing chapters + one `.product-playbook-state.json`.
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
  --check-state --drift
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

Eval fixture: [`evals/`](evals/). Schemas: [`schemas/`](schemas/).

## License

MIT. Issues: [github.com/b-amir/product-playbook/issues](https://github.com/b-amir/product-playbook/issues).
