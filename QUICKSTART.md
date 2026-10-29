# Product Playbook: quickstart

One page for any person or agent. You need Python 3.10+ and the product's code. Paths below are
examples. `pt` stands for `python3 <skill-dir>/scripts/playbook_tests.py`.

## Common jobs

| Job | Say to an agent | Or run |
| --- | --- | --- |
| Set up | "Write a test playbook for this repo, with runnable tests" | follow `SKILL.md` (intake, plan, write) |
| Test a ticket | "Test ABC-123 on dev" | `pt run tests --target dev --ticket ABC-123 --ticket-state "<state>" --source app=../app` |
| Test from pasted text | "Here is the ticket: ..." | `pt run tests --ticket-file ticket.md` |
| Retest a fix | "Retest ABC-123" | `pt retest tests --ticket ABC-123 --source app=../app` |
| What changed | "What should I rerun?" | `pt changed tests --source app=../app` |
| Smoke prod | "Smoke prod" | `pt run tests --target prod --tags smoke` |
| History | "How did ACC-02 do lately?" | `pt history tests --scenario ACC-02` |
| Manual result | "ACC-04 passed by hand" | add `--manual ACC-04=P` to the run |

No ticket? Leave the ticket flags out. No tracker? Paste the ticket text into a file.

## What the results mean

| | Result | Means | Next step |
| --- | --- | --- | --- |
| P | Pass | Works as described | none |
| F | Fail | Built, ready for testing, and wrong | file or reopen a bug |
| B | Blocked | Could not judge (account, data, device, timeout) | fix the setup, rerun |
| E | Blocked (environment) | The environment lacks a service (storage, queue, AI model) | tell the environment owner |
| U | Not built yet | Not in the code, or ticket not ready for testing | wait; not a bug |
| N | Not run | Manual-only or excluded on this target | run by hand if needed |

A retest also says **fixed**, **still failing** or **newly broken** compared with the last run.
Lines starting with **Assumption:** are decisions the run made for you; check them.

## Safety rules

- Never write to a tracker, chat, or email unless the user asks for that exact message.
  Read tickets, do not change them. Draft comments and hand them over.
- Never run destructive tests on prod. Prod runs smoke/safe only unless the user explicitly
  passes `--allow-destructive`.
- Credentials live in env vars, never in files, reports, or history.
- `changed` only suggests; nothing reruns unless asked.
- Run history stays in local files (`playbook-runs/`).

More: [references/runs.md](references/runs.md) (results, retest, judgment defaults) ·
[references/tests.md](references/tests.md) (config) · [SKILL.md](SKILL.md) (writing playbooks).
