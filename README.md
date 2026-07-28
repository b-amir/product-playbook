<p align="center">
  <img src="assets/readme/hero.svg" width="100%" alt="Product Playbook turns automated tests and source into evidence-backed manual testing scenarios">
</p>

<p align="center">
  <a href="https://skills.sh/b-amir/product-playbook"><img src="https://img.shields.io/badge/skills.sh-product--playbook-000000" alt="Install from skills.sh"></a>
  <a href="https://agentskills.io/"><img src="https://img.shields.io/badge/Agent%20Skills-compatible-111111" alt="Agent Skills compatible"></a>
  <a href="https://github.com/b-amir/product-playbook/actions/workflows/validate.yml"><img src="https://github.com/b-amir/product-playbook/actions/workflows/validate.yml/badge.svg" alt="Validate skill"></a>
  <img src="https://img.shields.io/badge/python-3.9%2B-3776AB?logo=python&logoColor=white" alt="Python 3.9+">
  <a href="LICENSE"><img src="https://img.shields.io/github/license/b-amir/product-playbook" alt="MIT license"></a>
</p>

<p align="center">
  <strong>Turn tests, contracts, source, and documentation into manual playbooks your team can run.</strong><br>
  A portable <a href="https://agentskills.io/">Agent Skill</a> for QA, product, support, and operations.
</p>

## Install

```bash
npx skills add b-amir/product-playbook
```

Works with agents that load `SKILL.md` skills, including Cursor, Claude Code, Codex, OpenCode, Gemini CLI, and GitHub Copilot via the [`skills` CLI](https://github.com/vercel-labs/skills). Codex also picks up the bundled [`agents/openai.yaml`](agents/openai.yaml) interface hints.

Then ask your agent:

```text
Use $product-playbook with source=product=./my-app and verify=false.
```

Sources may be local directories or Git repository URLs. Bundled helpers need Python 3.9+ and use only the standard library. Full workflow: [`SKILL.md`](SKILL.md).

<p align="center">
  <img src="assets/readme/workflow.svg" width="100%" alt="Product Playbook discovery, analysis, generation, validation, and reconciliation workflow">
</p>

## What it does

Product Playbook discovers product journeys from executable evidence and writes tester-facing scenarios with direct steps and observable pass criteria.

It supports:

- frontend, API, full-stack, CLI, service, worker, integration, and mobile products
- local directories and remote Git repositories
- monorepos and products split across several repositories
- playbooks stored inside a source repository or in a separate directory
- complete reconciliation when every component is accessible
- scoped contributions when a team can access only part of the product
- portable evidence state without machine-specific paths

## One-command bootstrap

```bash
python3 scripts/bootstrap_playbook.py \
  --source "web=./apps/web" \
  --source "api=./services/api" \
  --docs-source "docs=./docs" \
  --output-dir "./docs/playbook"
```

Bootstrap acquires remote repositories into a controlled workspace, discovers every accessible surface, finds tests and commands, identifies existing drafts, and reports the next action.

Add `--source-ref "api=v1.4.2"` to pin a Git branch, tag, or commit for any remote source.

After evidence analysis, render a new playbook deterministically:

```bash
python3 scripts/render_playbook.py ./evidence-plan.json ./docs/playbook
```

Existing drafts are reconciled with focused patches instead of being rendered again. See [`references/draft-reconciliation.md`](references/draft-reconciliation.md) and [`references/output-contract.md`](references/output-contract.md).

## Canonical output

```text
docs/playbook/
├── README.md
├── 01-checkout.md
├── 02-account.md
├── NN-quality-sweep.md
├── results-template.md
└── .product-playbook-state.json
```

The Markdown is tester-facing. The single hidden state file contains portable source-relative fingerprints used to reconcile later contributions. It contains no verification status, issues, authoring timestamps, decisions, or history. Publish only the Markdown files to testers.

To consolidate state created by versions that used `.product-playbook/`, run:

```bash
python3 scripts/inventory_playbook.py ./docs/playbook --migrate-state
```

## Team contributions

Every team reuses the same canonical output. A scoped run may add or update scenarios supported by its accessible sources, while preserving scenarios and evidence owned by unavailable sources. Details: [`references/collaboration-state.md`](references/collaboration-state.md).

```bash
python3 scripts/inventory_playbook.py ./docs/playbook \
  --source "api=./services/api" \
  --run-scope contribution \
  --scope api \
  --check-state \
  --output ./inventory.json
```

Capture `state_digest` from `inventory.json`, update the Markdown and internal evidence ledger, then write state:

```bash
python3 scripts/validate_playbook.py ./docs/playbook

python3 scripts/inventory_playbook.py ./docs/playbook \
  --source "api=./services/api" \
  --run-scope contribution \
  --scope api \
  --evidence-ledger ./ledger.json \
  --base-state-digest "$STATE_DIGEST" \
  --write-state

python3 scripts/validate_playbook.py ./docs/playbook --require-state
```

The state digest prevents a stale contribution from overwriting newer work. Full reconciliation is required before removing scenarios.

## Validation

```bash
python3 -m unittest discover -s tests -v
```

CI runs the same suite on Python 3.9 and 3.13 via [`.github/workflows/validate.yml`](.github/workflows/validate.yml). Coverage includes mixed surfaces, unfamiliar toolchains, remote acquisition, portable state, and strict output validation.

## Reporting problems

Open an issue at [github.com/b-amir/product-playbook/issues](https://github.com/b-amir/product-playbook/issues). Include the agent and operating system, redact sensitive paths, and attach the relevant helper output.

## License

MIT. See [LICENSE](LICENSE).
