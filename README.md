# Product Playbook

[![skills.sh](https://skills.sh/b/b-amir/product-playbook)](https://skills.sh/b-amir/product-playbook)

An [Agent Skill](https://agentskills.io/) that turns automated tests, contracts, source code, and docs into **tester-facing manual playbooks**. QA, product owners, support, and operators get step-by-step scenarios they can run through the product UI or supported interface. Evidence ledgers and verification status stay in agent chat or `.product-playbook-state.json`, not in the published Markdown.

## What it does

- **Discovers** product surfaces, test frameworks, routes, roles, and existing playbook drafts
- **Creates** a fresh playbook from behavioral evidence when none exists
- **Reconciles** an existing draft when code, tests, or docs change
- **Validates** structure, links, and output contract before saving
- **Optionally verifies** scenarios by running tests or driving the interface

Supported surfaces include frontend, API, full-stack, CLI, service, worker, integration, and mobile projects.

## Supported agents

This skill follows the open [Agent Skills](https://agentskills.io/) format and installs through the [`skills` CLI](https://github.com/vercel-labs/skills). It works with agents that load `SKILL.md` skills, including:

- **Cursor** (Agent Skills)
- **Claude Code** and **Claude.ai** (custom skills)
- **Codex** (via bundled `agents/openai.yaml` interface hints)
- **OpenCode**, **Gemini CLI**, **GitHub Copilot**, and other agents supported by the `skills` CLI

After install, invoke the skill when you need manual test documentation or playbook reconciliation.

## Requirements

- **Python 3.9+** for bundled helper scripts (`discover_product.py`, `inventory_playbook.py`, `validate_playbook.py`)
- Read access to your product code repo and optional docs repo
- No extra pip packages (scripts use the Python standard library only)

## Installation

```bash
npx skills add b-amir/product-playbook
```

List available skills before installing:

```bash
npx skills add b-amir/product-playbook --list
```

## Usage

Once installed, ask your agent to use the skill with your project paths.

### Create a new playbook

```text
Use $product-playbook to create a manual testing playbook for my app.

code_repo=/path/to/my-app
docs_path=/path/to/my-docs
output_dir=/path/to/my-docs/playbook
product_surface=auto
verify=false
```

### Reconcile an existing playbook

```text
Use $product-playbook to reconcile the playbook at /path/to/docs/playbook
against the current frontend tests. Run verification where safe.

code_repo=/path/to/my-app
docs_path=/path/to/my-docs
output_dir=/path/to/docs/playbook
mode=reconcile
verify=true
```

### Minimal single-repo setup

With one code repo and no separate docs root, the default output is `<code-repo>/docs/playbook`:

```text
Use $product-playbook with code_repo=/path/to/my-app and verify=false.
```

### When to pass `output_dir`

Pass `output_dir` explicitly when:

- More than one evidence root is involved (code + docs repos)
- The playbook should live outside the app repo
- Discovery finds multiple draft candidates

The skill asks before writing when the destination is ambiguous.

## What you get

The skill produces a portable playbook folder:

```text
<output_dir>/
├── README.md                 # Hub with smoke path and account checklist
├── 01-<journey>.md           # Journey chapters with numbered scenarios
├── results-template.md       # Reusable run record
└── .product-playbook-state.json   # Internal evidence state (not for testers)
```

Published Markdown stays **tester-facing only**. No source paths, verification indexes, or gap markers appear in the playbook your team reads.

## Skill structure

```text
product-playbook/
├── SKILL.md              # Agent instructions (required)
├── README.md             # This file
├── LICENSE
├── scripts/
│   ├── discover_product.py
│   ├── inventory_playbook.py
│   └── validate_playbook.py
├── references/
│   ├── draft-reconciliation.md
│   ├── framework-discovery.md
│   └── output-contract.md
└── agents/
    └── openai.yaml       # Optional Codex interface hints
```

## Reporting problems

Open an issue on GitHub:

**https://github.com/b-amir/product-playbook/issues**

Include:

- Agent and OS version
- `code_repo`, `docs_path`, and `output_dir` you used (redact secrets)
- Whether you ran with `verify=true`
- Relevant script output or agent error messages

## License

MIT. See [LICENSE](./LICENSE).
