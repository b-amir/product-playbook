<p align="center">
  <img src="https://raw.githubusercontent.com/b-amir/product-playbook/main/assets/readme/hero.svg" width="100%" alt="Product Playbook turns automated tests and source into evidence-backed manual testing scenarios">
</p>

<p align="center">
  <a href="https://skills.sh/b-amir/product-playbook"><img src="https://img.shields.io/badge/skills.sh-product--playbook-000000" alt="skills.sh"></a>
  <a href="https://agentskills.io/"><img src="https://img.shields.io/badge/format-Agent%20Skills-44403c" alt="Agent Skills format"></a>
  <a href="./LICENSE"><img src="https://img.shields.io/badge/license-MIT-166534" alt="MIT License"></a>
</p>

<p align="center">
  <strong>Turn tests, contracts, and source into manual playbooks your team can run.</strong><br>
  An <a href="https://agentskills.io/">Agent Skill</a> for QA, product, support, and ops.
</p>

## Install

```bash
npx skills add b-amir/product-playbook
```

Then ask your agent:

```text
Use $product-playbook with code_repo=/path/to/my-app and verify=false.
```

Requires **Python 3.9+** for bundled helper scripts. No extra pip packages.

<p align="center">
  <img src="https://raw.githubusercontent.com/b-amir/product-playbook/main/assets/readme/workflow.svg" width="100%" alt="Seven-phase pipeline from discovery through validation">
</p>

## Why this exists

Automated tests already describe how the product should behave. Product Playbook extracts that evidence and writes **tester-facing scenarios** with clear steps and pass criteria.

The published Markdown stays readable for non-engineers. Evidence status, source paths, and reconciliation notes stay in agent chat or `.product-playbook-state.json`.

## What you get

```text
<output_dir>/
├── README.md                      # Hub with smoke path and setup checklist
├── 01-<journey>.md                # Journey chapters with numbered scenarios
├── results-template.md            # Reusable run record
└── .product-playbook-state.json   # Internal evidence state (not for testers)
```

Each scenario includes setup, ordered actions, observable pass criteria, and cleanup when evidence establishes it.

## Usage

### Create a playbook

```text
Use $product-playbook to create a manual testing playbook for my app.

code_repo=/path/to/my-app
docs_path=/path/to/my-docs
output_dir=/path/to/my-docs/playbook
product_surface=auto
verify=false
```

### Reconcile an existing draft

```text
Use $product-playbook to reconcile the playbook at /path/to/docs/playbook.

code_repo=/path/to/my-app
docs_path=/path/to/my-docs
output_dir=/path/to/docs/playbook
mode=reconcile
verify=true
```

Pass `output_dir` when more than one evidence root is involved or when the playbook should live outside the app repo. With one code repo and no docs root, the default is `<code-repo>/docs/playbook`.

<details>
<summary><strong>More examples</strong></summary>

List skills before installing:

```bash
npx skills add b-amir/product-playbook --list
```

Minimal single-repo prompt:

```text
Use $product-playbook with code_repo=/path/to/my-app and verify=false.
```

</details>

## Supported surfaces and agents

| Surfaces | Frontend, API, full-stack, CLI, service, worker, integration, mobile |
| -------- | --------------------------------------------------------------------- |
| Agents   | Cursor, Claude Code, Claude.ai, Codex, GitHub Copilot, OpenCode, Gemini CLI, and others via the [`skills` CLI](https://github.com/vercel-labs/skills) |

## Repository layout

```text
product-playbook/
├── SKILL.md              # Agent instructions
├── scripts/              # discover, inventory, validate helpers
├── references/           # reconciliation and output contract docs
└── agents/openai.yaml    # Optional Codex interface hints
```

## Reporting problems

Open an issue at [github.com/b-amir/product-playbook/issues](https://github.com/b-amir/product-playbook/issues).

Include your agent and OS, the paths you used (redact secrets), whether `verify=true`, and any script output.

## License

MIT. See [LICENSE](./LICENSE).
