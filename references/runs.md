# Runs: readiness, tickets, history, retest, what changed

How to run a playbook's tests against a ticket or a fix, and how to read the result. Everything
here works without a tracker, a board, a branching model, or CI. When one of those exists, use
it as an input. Never assume it.

## Contents

- [Results](#results)
- [Readiness before Fail](#readiness-before-fail)
- [Ticket-pinned runs](#ticket-pinned-runs)
- [Run history](#run-history)
- [Retest a fix](#retest-a-fix)
- [What changed since the last run](#what-changed-since-the-last-run)
- [Judgment fallbacks](#judgment-fallbacks)

## Results

| Letter | Result | Meaning | Who acts |
| --- | --- | --- | --- |
| P | Pass | Behaves as the scenario expects | nobody |
| F | Fail | The feature exists, is ready for testing, and misbehaves | developer (bug) |
| B | Blocked | Could not be judged: missing account, data, device, timeout, every test skipped | tester |
| E | Blocked (environment) | The target lacks a capability (storage, queue, paid model) | environment owner |
| U | Not built yet | The feature is not in the code under test, or its ticket is not ready for testing | nobody yet |
| N | Not run | Manual-only, or excluded by tags on this target | tester |

Only F is a defect. Exit code 1 means at least one F.

## Readiness before Fail

Before you report F, confirm the thing exists and is meant to work:

1. **In the code.** Scenarios may list `readiness` markers: a file and, optionally, a regex it
   must contain (a route, a flag, a symbol). With `--source ID=PATH` the runner checks them first
   and records **U** without running when one is absent. A test can also detect a missing
   feature itself and skip with a `[not-built] <reason>` line.
2. **On the ticket.** If you know the ticket state, pass `--ticket-state "<state>"`. When the
   config lists `tickets.ready_states` and the state is not one of them, failures become **U**
   with the state in the note. No state known: skip this step and say so.
3. **Without markers.** When a scenario has no markers, look yourself: search the code for the
   route, screen, or command. Missing means U, present means F. State which you did.

## Ticket-pinned runs

The ticket is optional and can come from anywhere:

| You have | Pass |
| --- | --- |
| an ID | `--ticket ABC-123` |
| pasted text or an export | `--ticket-file ticket.md` or `--ticket-text "..."` (the first ID-like token that is not a scenario or EX ID becomes the reference) |
| a tracker connector | read the ticket with it, then pass the ID, state and text as above. Read only |
| nothing | omit it; the run is pinned to commits and time only |

Selection: scenarios whose `tickets` list contains the reference, plus scenario IDs or
acceptance IDs named in the ticket text. `--only` overrides. Nothing linked: the normal selection
runs and the report says so as an Assumption.

Every run records the target, its kind, a timestamp with offset, and the commit of each
`--source` checkout and of the tests folder (`+uncommitted` when the tree is dirty). Only the
ticket reference, title, state and a hash of its text are kept; never the full text.

## Run history

Each `run` and `retest` writes `<tests_dir>/<history_dir>/<run_id>.json` (default folder
`playbook-runs`, shape in `schemas/run-record.schema.json`). It is local. Add the folder to
`.gitignore` unless the team wants to share history. `--no-history` skips the record.

```bash
playbook_tests.py history <tests_dir>                       # recent runs, counts, commits
playbook_tests.py history <tests_dir> --ticket ABC-123      # one ticket
playbook_tests.py history <tests_dir> --scenario ACC-02     # one scenario over time
```

Every run on a target that has an earlier run covering the same scenarios prints a
**Since last run** line: fixed, still failing, newly broken, and other letter changes.

## Retest a fix

```bash
playbook_tests.py retest <tests_dir> --ticket ABC-123 --source app=../app
```

Scope, first match wins: `--only`; the ticket's scenarios; else everything that was not P in the
last run on that target. Then it adds **neighbours**: scenarios sharing a test file, an evidence
file, or an acceptance story (`EX-9.1-*`). They are marked "regression check" in the notes.
`--no-neighbours` turns that off. The diff reports fixed / still failing / newly broken.

## What changed since the last run

```bash
playbook_tests.py changed <tests_dir> --source app=../app [--since app=<commit>]
```

Runs nothing. For each source it diffs from `--since` or the commit recorded by the last run,
adds uncommitted files, and maps them to scenarios through `evidence` and `readiness` paths. It
also flags scenarios whose test file changed. Unmapped files are listed so you can judge whether
a smoke run is worth it. Without git, it falls back to the evidence fingerprints. The output
ends with a suggested `retest` command. Run it only if the user wants.

## Judgment fallbacks

When something is unclear, decide, write the decision as an Assumption line in the report, and
carry on. Ask only when the choice is destructive or touches prod.

| Unclear | Default |
| --- | --- |
| Which target | `default_target`, else local. Never prod unless named |
| Which ticket scenarios | Linked + mentioned; none found, run smoke+safe and say so |
| Failure but code may be missing | Search the code; absent means U, present means F |
| Ticket state unknown | Do not guess; treat the failure as F and note "ticket state not checked" |
| Ticket says done but code differs from commit tested | Report the commit you tested; suggest retesting on the right one |
| Flaky (passes on rerun) | Report F with "flaky: passed 1 of 2" unless the team's rule says otherwise |
| No earlier run to diff | Run normally; the next run will diff |
| Environment or code? | Missing service, credential, or quota is E; wrong behaviour on a working service is F |
| Changed file maps to nothing | List it; suggest smoke only when it is shared code (auth, config, routing) |
