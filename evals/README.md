# Eval fixture

Tiny fake product used to score agent runs of this skill.

## Layout

```text
evals/fixture-product/
├── README.md
├── openapi.yaml
├── app.py                 # trivial in-memory API
└── tests/test_accounts.py
├── acceptance.md          # Given/When/Then examples EX-1.1-1, EX-1.1-2
evals/reference/
├── plan.json              # reference plan with automation opt-in
└── playbook-tests/        # reference generated tests + playbook-tests.json
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

### Runnable-tests variant

Answer Intake question 4 with **C** and pass `evals/fixture-product/acceptance.md`. Then:

```bash
(cd evals/fixture-product && PORT=8765 python3 app.py &)
python3 scripts/score_eval.py evals/fixture-product/docs/playbook \
  --tests-dir evals/fixture-product/docs/playbook-tests
python3 scripts/playbook_tests.py run evals/fixture-product/docs/playbook-tests --target local
```

Pass requires: valid `playbook-tests.json` outside the playbook folder, a runnable test for
`ACC-01`, `EX-1.1-1` mapped, no literal credentials or machine paths, and every automated
scenario P against the running fixture. `evals/reference/` is the golden answer and is exercised
by `tests/test_playbook_tests.py`.
