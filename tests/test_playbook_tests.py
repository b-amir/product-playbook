from __future__ import annotations

import copy
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
FIXTURE = ROOT / "evals" / "fixture-product"
REFERENCE = ROOT / "evals" / "reference"
sys.path.insert(0, str(SCRIPTS))

import playbook_tests  # noqa: E402


def run(script: str, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / script), *args],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", **(env or {})},
    )


def reference_config() -> dict:
    return json.loads((REFERENCE / "playbook-tests" / "playbook-tests.json").read_text())


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class ConfigTests(unittest.TestCase):
    def test_reference_config_is_valid(self) -> None:
        errors = playbook_tests.check_config(
            reference_config(), REFERENCE / "playbook-tests", {"ACC-01", "ACC-02"}
        )
        self.assertEqual(errors, [])

    def test_rejects_literal_credentials_and_prod_urls(self) -> None:
        config = reference_config()
        config["targets"]["prod"] = {"kind": "prod", "base_url": "https://prod.example"}
        config["targets"]["dev"]["api_token"] = "abc123"
        config["targets"]["local"]["base_url"] = "http://user:pw@127.0.0.1:8765"
        errors = "\n".join(playbook_tests.check_config(config))
        self.assertIn("prod: use base_url_env", errors)
        self.assertIn("literal credential", errors)
        self.assertIn("embeds credentials", errors)

    def test_rejects_unbacked_or_unknown_ids(self) -> None:
        config = reference_config()
        config["scenarios"]["ACC-01"]["evidence"] = []
        config["scenarios"]["ACC-02"]["acceptance"] = ["EX-9.9-9"]
        config["scenarios"]["ACC-03"] = {"manual_only": True}
        errors = "\n".join(playbook_tests.check_config(config, None, {"ACC-01", "ACC-02"}))
        self.assertIn("ACC-01 needs evidence", errors)
        self.assertIn("unknown acceptance example EX-9.9-9", errors)
        self.assertIn("ACC-03 is not a scenario", errors)
        self.assertIn("ACC-03 is manual_only and needs a reason", errors)

    def test_acceptance_parser_reads_given_when_then(self) -> None:
        examples = playbook_tests.parse_acceptance(
            "### EX-9.1-9: Archive a project\n"
            "Given an owner\nAnd an active project\n"
            "When they click **Archive**\nThen the project is read-only\n"
            "| EX-9.1-10 | Restore |\n- Given an archived project\n"
        )
        self.assertEqual(sorted(examples), ["EX-9.1-10", "EX-9.1-9"])
        self.assertEqual(examples["EX-9.1-9"]["given"], "an owner; an active project")
        self.assertEqual(examples["EX-9.1-9"]["then"], "the project is read-only")
        self.assertEqual(examples["EX-9.1-9"]["title"], "Archive a project")

    def test_prod_runs_only_safe_or_smoke_without_destructive(self) -> None:
        select = playbook_tests.select
        self.assertIsNotNone(select({"tags": ["smoke", "destructive"]}, "prod", set(), False))
        self.assertIsNone(select({"tags": ["smoke", "destructive"]}, "prod", set(), True))
        self.assertIsNone(select({"tags": ["safe"]}, "prod", set(), False))
        self.assertIsNone(select({"tags": ["destructive"]}, "local", set(), False))
        self.assertIsNotNone(select({"tags": ["safe"]}, "local", {"smoke"}, False))

    def test_plan_automation_is_validated(self) -> None:
        plan = json.loads((REFERENCE / "plan.json").read_text())
        bad = copy.deepcopy(plan)
        bad["chapters"][0]["scenarios"][0]["automation"] = {"tags": ["smoke", "fast"]}
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "plan.json"
            path.write_text(json.dumps(bad))
            self.assertNotEqual(run("schema_utils.py", str(path)).returncode, 0)
            path.write_text(json.dumps(plan))
            self.assertEqual(run("schema_utils.py", str(path)).returncode, 0)


class EnvironmentCapabilityTests(unittest.TestCase):
    """requires/provides: unmet environment needs are E (Blocked, environment), never F."""

    def config(self) -> dict:
        ok = ["{python}", "-c", "print('1 passed')"]
        env_skip = ["{python}", "-c", "print('[env] needs sqs: no queue configured'); print('1 skipped')"]
        evidence = [{"source_id": "app", "path": "app.py"}]
        return {
            "managed_by": "product-playbook",
            "capabilities": {"s3": "object storage", "sqs": "queue", "llm-real": "paid LLM"},
            "default_target": "local",
            "targets": {
                "local": {"kind": "local", "base_url": "http://127.0.0.1:1", "provides": ["s3"]},
                "dev": {"kind": "dev", "base_url_env": "QA_DEV_URL", "provides": ["s3", "sqs", "llm-real"]},
            },
            "scenarios": {
                "UPL-01": {"tags": ["safe"], "test": "t.py", "run": ok, "evidence": evidence, "requires": ["s3"]},
                "JOB-01": {"tags": ["safe"], "test": "t.py", "run": ok, "evidence": evidence, "requires": ["sqs"]},
                "OCR-01": {"tags": ["safe"], "test": "t.py", "run": env_skip, "evidence": evidence},
                "ACC-01": {"tags": ["safe"], "test": "t.py", "run": ["{python}", "-c", "raise SystemExit(1)"], "evidence": evidence},
            },
        }

    def write(self, config: dict) -> Path:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        (root / "t.py").write_text("")
        (root / "playbook-tests.json").write_text(json.dumps(config))
        self.addCleanup(self.temporary.cleanup)
        return root

    def test_capabilities_are_validated(self) -> None:
        config = self.config()
        self.assertEqual(playbook_tests.check_config(config), [])
        config["targets"]["local"]["provides"] = ["S3", "redis"]
        config["scenarios"]["UPL-01"]["requires"] = "s3"
        errors = "\n".join(playbook_tests.check_config(config))
        self.assertIn("bad capability name 'S3'", errors)
        self.assertIn("'redis' is not declared", errors)
        self.assertIn("UPL-01 requires must be a list", errors)

    def test_missing_capability_is_env_blocked_not_fail(self) -> None:
        root = self.write(self.config())
        result = run("playbook_tests.py", "run", str(root), "--json")
        self.assertEqual(result.returncode, 1, result.stderr)  # ACC-01 is a real failure
        data = json.loads(result.stdout)
        results = data["results"]
        self.assertEqual(data["provides"], ["s3"])
        self.assertEqual(results["UPL-01"]["result"], "pass")
        self.assertEqual(results["JOB-01"], {"result": "env", "mode": "Auto", "note": "target lacks sqs"})
        self.assertEqual(results["OCR-01"]["result"], "env")
        self.assertIn("needs sqs", results["OCR-01"]["note"])
        self.assertEqual(results["ACC-01"]["result"], "fail")

    def test_provide_flag_and_report_separate_environment_from_code(self) -> None:
        root = self.write(self.config())
        result = run("playbook_tests.py", "run", str(root), "--provide", "sqs", "--only", "JOB-01,OCR-01")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("| JOB-01 | P | Auto |", result.stdout)
        self.assertIn("| OCR-01 | E | Auto |", result.stdout)
        self.assertIn("P 1 · F 0 · B 0 · E 1 · U 0 · N 0", result.stdout)
        self.assertIn("Environment: 1 blocked by the target, not by code (OCR-01)", result.stdout)
        bad = run("playbook_tests.py", "run", str(root), "--provide", "kafka")
        self.assertEqual(bad.returncode, 2)

    def test_environment_section_renders_and_validates(self) -> None:
        plan = json.loads((REFERENCE / "plan.json").read_text())
        scenario = plan["chapters"][0]["scenarios"][0]
        scenario["environment"] = ["Needs real object storage"]
        scenario.setdefault("automation", {})["requires"] = ["s3"]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "plan.json"
            path.write_text(json.dumps(plan))
            self.assertEqual(run("schema_utils.py", str(path)).returncode, 0)
            out = Path(temporary) / "playbook"
            result = run("render_playbook.py", str(path), str(out))
            self.assertEqual(result.returncode, 0, result.stderr)
            text = "".join(p.read_text() for p in out.glob("[0-9][0-9]-*.md"))
            self.assertIn("**Environment**\n\n- Needs real object storage", text)
            validate = run("validate_playbook.py", str(out))
            self.assertEqual(validate.returncode, 0, validate.stdout)
            scenario["automation"]["requires"] = ["S3"]
            path.write_text(json.dumps(plan))
            self.assertNotEqual(run("schema_utils.py", str(path)).returncode, 0)

    def test_manual_env_result(self) -> None:
        results: dict = {}
        playbook_tests.merge_manual(results, ["OCR-02=E:needs real Azure"])
        self.assertEqual(results["OCR-02"]["result"], "env")


class FixtureRunTests(unittest.TestCase):
    """Render the reference fixture plan, then run its generated tests for real."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.product = self.root / "product"
        shutil.copytree(FIXTURE, self.product, ignore=shutil.ignore_patterns("__pycache__", "docs"))
        self.playbook = self.product / "docs" / "playbook"
        self.tests_dir = self.product / "docs" / "playbook-tests"
        result = run("render_playbook.py", str(REFERENCE / "plan.json"), str(self.playbook))
        self.assertEqual(result.returncode, 0, result.stderr)
        shutil.copytree(REFERENCE / "playbook-tests", self.tests_dir)
        self.port = free_port()
        self.server = subprocess.Popen(
            [sys.executable, "app.py"],
            cwd=self.product,
            env={**os.environ, "PORT": str(self.port)},
        )
        deadline = time.time() + 5
        while time.time() < deadline:
            try:
                socket.create_connection(("127.0.0.1", self.port), timeout=0.2).close()
                break
            except OSError:
                time.sleep(0.05)

    def tearDown(self) -> None:
        self.server.terminate()
        self.server.wait(timeout=5)
        self.temporary.cleanup()

    def test_generated_tests_run_and_pass_with_short_report(self) -> None:
        validate = run(
            "validate_playbook.py", str(self.playbook), "--tests-dir", str(self.tests_dir)
        )
        self.assertEqual(validate.returncode, 0, validate.stdout)
        report = self.root / "report.md"
        result = run(
            "playbook_tests.py", "run", str(self.tests_dir),
            "--base-url", f"http://127.0.0.1:{self.port}",
            "--manual", "ACC-03=B:no device",
            "--output", str(report),
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        text = report.read_text()
        self.assertIn("| ACC-01 | P | Auto | EX-1.1-1 |", text)
        self.assertIn("| ACC-02 | P | Auto | EX-1.1-2 |", text)
        self.assertIn("| ACC-03 | B | Manual |", text)
        self.assertIn("Acceptance: 2/2 examples mapped", text)
        self.assertLess(len(text.splitlines()), 15)

    def test_prod_target_needs_env_and_skips_destructive(self) -> None:
        missing = run("playbook_tests.py", "run", str(self.tests_dir), "--target", "prod")
        self.assertEqual(missing.returncode, 2)
        result = run(
            "playbook_tests.py", "run", str(self.tests_dir), "--target", "prod", "--json",
            env={"PLAYBOOK_PROD_URL": f"http://127.0.0.1:{self.port}"},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        results = json.loads(result.stdout)["results"]
        self.assertEqual(results["ACC-01"]["result"], "na")
        self.assertEqual(results["ACC-02"]["result"], "pass")

    def test_failing_target_reports_fail(self) -> None:
        result = run(
            "playbook_tests.py", "run", str(self.tests_dir),
            "--base-url", f"http://127.0.0.1:{free_port()}", "--only", "ACC-02",
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("| ACC-02 | F | Auto |", result.stdout)

    def test_drift_flags_tests_whose_evidence_changed(self) -> None:
        source = f"product={self.product}"
        clean = run("playbook_tests.py", "drift", str(self.tests_dir), "--source", source)
        self.assertEqual(clean.returncode, 0, clean.stdout)
        with (self.product / "app.py").open("a") as handle:
            handle.write("\n# changed\n")
        dirty = run("playbook_tests.py", "drift", str(self.tests_dir), "--source", source)
        self.assertEqual(dirty.returncode, 1)
        stale = json.loads(dirty.stdout)["stale_tests"]
        self.assertEqual(sorted(stale), ["ACC-02"])
        inventory = run(
            "inventory_playbook.py", str(self.playbook), "--source", source,
            "--check-state", "--drift", "--tests-dir", str(self.tests_dir),
        )
        self.assertEqual(inventory.returncode, 1)
        summary = json.loads(inventory.stdout)["drift_summary"]
        self.assertIn("ACC-02", summary["stale_tests"])
        # Re-fingerprint after review clears the drift.
        self.assertEqual(
            run("playbook_tests.py", "fingerprint", str(self.tests_dir), "--source", source).returncode, 0
        )
        self.assertEqual(
            run("playbook_tests.py", "drift", str(self.tests_dir), "--source", source).returncode, 0
        )

    def test_tests_inside_playbook_folder_are_rejected(self) -> None:
        inside = self.playbook / "tests"
        shutil.copytree(self.tests_dir, inside)
        result = run("validate_playbook.py", str(self.playbook), "--tests-dir", str(inside))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("tests-inside-playbook", result.stdout)

    def test_score_eval_scores_generated_tests(self) -> None:
        state = self.root / "ledger.json"
        state.write_text(json.dumps({"scenarios": {
            "ACC-01": {"status": "SOURCED", "sources": [{"source_id": "product", "path": "openapi.yaml"}]},
            "ACC-02": {"status": "SOURCED", "sources": [{"source_id": "product", "path": "app.py"}]},
        }}))
        written = run(
            "inventory_playbook.py", str(self.playbook), "--source", f"product={self.product}",
            "--evidence-ledger", str(state), "--write-state",
        )
        self.assertEqual(written.returncode, 0, written.stderr)
        result = run(
            "score_eval.py", str(self.playbook), "--tests-dir", str(self.tests_dir)
        )
        self.assertEqual(result.returncode, 0, result.stdout)


if __name__ == "__main__":
    unittest.main()


class RunHistoryTests(unittest.TestCase):
    """Readiness, ticket-pinned runs, retest diffs and what-changed mapping."""

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.tests = self.root / "tests"
        self.code = self.root / "code"
        self.tests.mkdir()
        (self.code / "app").mkdir(parents=True)
        (self.code / "app" / "routes.py").write_text("ROUTES = ['/login']\n")
        (self.code / "app" / "other.py").write_text("x = 1\n")
        self.git(self.code, "init", "-q")
        self.git(self.code, "add", ".")
        self.git(self.code, "-c", "user.email=a@b", "-c", "user.name=t", "commit", "-qm", "one")
        (self.tests / "t.py").write_text("")
        (self.tests / "flag").write_text("fail")
        flagged = ["{python}", "-c",
                   "import pathlib,sys; sys.exit(pathlib.Path('flag').read_text()=='fail')"]
        ok = ["{python}", "-c", "pass"]
        ev = [{"source_id": "app", "path": "app/routes.py"}]
        self.config = {
            "managed_by": "product-playbook",
            "default_target": "local",
            "targets": {"local": {"kind": "local", "base_url": "http://127.0.0.1:1"}},
            "tickets": {"ready_states": ["Test", "Done"]},
            "acceptance": {"EX-1.1-1": {"title": "login works"}},
            "scenarios": {
                "LOG-01": {"tags": ["safe"], "test": "t.py", "run": flagged, "evidence": ev,
                           "tickets": ["ABC-7"], "acceptance": ["EX-1.1-1"]},
                "LOG-02": {"tags": ["safe"], "test": "t.py", "run": ok, "evidence": ev},
                "PAY-01": {"tags": ["safe"], "test": "p.py", "run": ok,
                           "evidence": [{"source_id": "app", "path": "app/pay.py"}],
                           "readiness": [{"source_id": "app", "path": "app/pay.py"}]},
                "SIG-01": {"tags": ["safe"], "test": "p.py", "run": ok,
                           "evidence": [{"source_id": "app", "path": "app/other.py"}],
                           "readiness": [{"source_id": "app", "path": "app/routes.py",
                                          "contains": "/signup"}]},
                "NB-01": {"tags": ["safe"], "test": "p.py", "evidence": ev,
                          "run": ["{python}", "-c", "print('[not-built] no /export route'); print('1 skipped')"]},
            },
        }
        (self.tests / "p.py").write_text("")
        (self.tests / "playbook-tests.json").write_text(json.dumps(self.config))

    @staticmethod
    def git(root: Path, *args: str) -> None:
        subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)

    def pb(self, *args: str) -> subprocess.CompletedProcess[str]:
        return run("playbook_tests.py", *args)

    def test_config_validates_new_fields(self) -> None:
        self.assertEqual(playbook_tests.check_config(self.config, self.tests), [])
        bad = copy.deepcopy(self.config)
        bad["scenarios"]["LOG-01"]["tickets"] = "ABC-7"
        bad["scenarios"]["PAY-01"]["readiness"] = [{"path": "/abs"}]
        bad["history_dir"] = "../out"
        errors = "\n".join(playbook_tests.check_config(bad))
        self.assertIn("LOG-01 tickets must be a list", errors)
        self.assertIn("PAY-01 readiness items need", errors)
        self.assertIn("history_dir must be", errors)

    def test_readiness_and_marker_give_not_built(self) -> None:
        result = self.pb("run", str(self.tests), "--source", f"app={self.code}",
                         "--only", "PAY-01,SIG-01,NB-01,LOG-02", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        res = data["results"]
        self.assertEqual(res["PAY-01"]["result"], "unbuilt")
        self.assertIn("app/pay.py missing", res["PAY-01"]["note"])
        self.assertEqual(res["SIG-01"]["result"], "unbuilt")
        self.assertEqual(res["NB-01"]["result"], "unbuilt")
        self.assertIn("/export", res["NB-01"]["note"])
        self.assertEqual(res["LOG-02"]["result"], "pass")
        self.assertEqual(len(data["commits"]["app"]["sha"]), 40)
        self.assertFalse(data["commits"]["app"]["dirty"])

    def test_without_source_readiness_is_not_checked(self) -> None:
        data = json.loads(self.pb("run", str(self.tests), "--only", "PAY-01", "--json").stdout)
        self.assertEqual(data["results"]["PAY-01"]["result"], "pass")

    def test_ticket_selects_linked_scenarios_and_state_downgrades_fail(self) -> None:
        result = self.pb("run", str(self.tests), "--ticket", "ABC-7", "--ticket-state", "In Progress")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Ticket ABC-7 · state In Progress", result.stdout)
        self.assertIn("| LOG-01 | U |", result.stdout)
        self.assertNotIn("LOG-02", result.stdout)
        ready = self.pb("run", str(self.tests), "--ticket", "ABC-7", "--ticket-state", "Test")
        self.assertEqual(ready.returncode, 1)
        self.assertIn("| LOG-01 | F |", ready.stdout)

    def test_ticket_text_file_finds_ref_and_mentions(self) -> None:
        ticket = self.root / "ticket.md"
        ticket.write_text("# Fix signup copy\nKey: XYZ-42\nSee EX-1.1-1 and LOG-02.\n")
        data = json.loads(self.pb("run", str(self.tests), "--ticket-file", str(ticket), "--json").stdout)
        self.assertEqual(data["ticket"]["ref"], "XYZ-42")
        self.assertEqual(data["ticket"]["title"], "Fix signup copy")
        self.assertEqual(set(data["results"]), {"LOG-01", "LOG-02"})
        self.assertNotIn("text", data["ticket"])

    def test_unlinked_ticket_states_assumption(self) -> None:
        result = self.pb("run", str(self.tests), "--ticket", "ZZZ-1", "--only", "LOG-02")
        self.assertNotIn("Assumption", result.stdout)
        result = self.pb("run", str(self.tests), "--ticket", "ZZZ-1", "--tags", "safe")
        self.assertIn("Assumption: no scenario is linked to ticket ZZZ-1", result.stdout)

    def test_history_retest_diff_and_neighbours(self) -> None:
        first = self.pb("run", str(self.tests), "--only", "LOG-01,LOG-02")
        self.assertEqual(first.returncode, 1)
        nothing = self.pb("retest", str(self.tests), "--target", "local", "--no-history",
                          "--only", "LOG-02")
        self.assertEqual(nothing.returncode, 1)  # LOG-01 rides along as a neighbour
        self.assertIn("regression check", nothing.stdout)
        (self.tests / "flag").write_text("ok")
        retest = self.pb("retest", str(self.tests), "--json")
        self.assertEqual(retest.returncode, 0, retest.stderr)
        data = json.loads(retest.stdout)
        self.assertEqual(data["comparison"]["fixed"], ["LOG-01"])
        self.assertEqual(data["results"]["LOG-02"]["scope"], "neighbour")
        self.assertIn("NB-01", data["results"])  # shares evidence
        (self.tests / "flag").write_text("fail")
        again = self.pb("retest", str(self.tests), "--only", "LOG-02")
        self.assertIn("LOG-01", again.stdout)  # neighbour via shared test file
        self.assertIn("newly broken 1 (LOG-01)", again.stdout)
        history = json.loads(self.pb("history", str(self.tests), "--scenario", "LOG-01").stdout)
        self.assertEqual([r["result"] for r in history["runs"]], ["F", "P", "F"])

    def test_retest_without_history_is_an_error(self) -> None:
        result = self.pb("retest", str(self.tests))
        self.assertEqual(result.returncode, 2)
        self.assertIn("nothing to retest", result.stderr)

    def test_changed_maps_commits_to_scenarios(self) -> None:
        self.pb("run", str(self.tests), "--source", f"app={self.code}", "--only", "LOG-02")
        (self.code / "app" / "routes.py").write_text("ROUTES = ['/login', '/signup']\n")
        (self.code / "README").write_text("docs\n")
        self.git(self.code, "add", ".")
        self.git(self.code, "-c", "user.email=a@b", "-c", "user.name=t", "commit", "-qm", "two")
        (self.code / "app" / "other.py").write_text("x = 2\n")  # uncommitted
        data = json.loads(self.pb("changed", str(self.tests), "--source", f"app={self.code}", "--json").stdout)
        self.assertEqual(set(data["affected"]), {"LOG-01", "LOG-02", "NB-01", "SIG-01"})
        self.assertEqual(data["unmapped"]["app"], ["README"])
        text = self.pb("changed", str(self.tests), "--source", f"app={self.code}").stdout
        self.assertIn("Suggested (not run)", text)
        runs = json.loads(self.pb("history", str(self.tests)).stdout)["runs"]
        self.assertEqual(len(runs), 1)  # changed runs nothing
