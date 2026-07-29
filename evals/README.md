# Eval fixture

Tiny fake product used to score agent runs of this skill.

## Layout

```text
evals/fixture-product/
├── README.md
├── openapi.yaml
├── app.py                 # trivial in-memory API
└── tests/test_accounts.py
evals/expected.json        # expectations for a successful create run
```

## How to score a run

1. Point the agent at `evals/fixture-product` with output `evals/fixture-product/docs/playbook`.
2. Allow Intake → Plan → Write (no live Agent-check required for the baseline eval).
3. Compare against `expected.json`:

- Required scenario IDs present
- Exact label **Create account** appears in steps (from the test/OpenAPI)
- No `## Sources`, `VERIFIED`, or `NEEDS VERIFICATION` in published Markdown
- `.product-playbook-state.json` exists with `managed_by: product-playbook`
- No files other than Markdown + state in the playbook directory (except optional export)

Fail the eval if the agent invents endpoints or button labels not in the fixture.
