from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def run_script(
    name: str,
    *args: str,
    check: bool = True,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / name), *args],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
        cwd=cwd,
    )
    if check and result.returncode != 0:
        raise AssertionError(result.stderr or result.stdout)
    return result


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")


def make_playbook(root: Path) -> None:
    write(
        root / "README.md",
        """
        # Product Playbook

        ## Test pass table
        | Pass | Use |
        | --- | --- |
        | Smoke | Basic coverage |

        ## Playbook map
        - [Account journey](01-account.md)

        ## Actors and test data
        | Actor | Data |
        | --- | --- |
        | Tester | Fixture account |

        ## Before you start
        1. Prepare the fixture.

        ## Environment handoff
        Use the test environment.

        ## Interface reference
        Use the supported API client.

        ## Run a scenario
        Follow the steps and expected results.

        ## Capture a failure
        Record the response.

        ## Severity guide
        Use Blocker, Major, Minor, or Cosmetic.

        ## Smoke path
        Run ACC-01.

        ## Full pass
        Run ACC-01.

        ## Sign-off
        Sign off after completion.
        """,
    )
    write(
        root / "01-account.md",
        """
        # Account journey

        ## Scenario list
        | ID | Scenario | Persona |
        | --- | --- | --- |
        | ACC-01 | List accounts | Tester |

        ## ACC-01: List accounts

        **Goal**

        List available accounts.

        **Who**

        Tester.

        **Steps**

        1. Send `GET /api/accounts`.

        **Expected**

        - The response status is `200`.

        ## Chapter checklist

        ```text
        ACC-01
        ```

        [Results](results-template.md)
        """,
    )
    write(
        root / "results-template.md",
        """
        # Results

        ## Run details
        Record the run.

        ## Environment coverage
        Record the client.

        ## Actors
        Record the tester.

        ## Test data
        Record the fixture.

        ## Legend
        Use P, F, B, or N.

        | ID | Result |
        | --- | --- |
        | ACC-01 | |

        ## Defects
        Record defects.

        ## Blocked and N/A
        Record blocked checks.

        ## Cleanup
        Record cleanup.

        ## Summary
        Summarize results.

        ## Sign-off
        Record approval.
        """,
    )


class DiscoveryTests(unittest.TestCase):
    def test_monorepo_reports_each_manifest_component(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write(
                root / "apps" / "web" / "package.json",
                """
                {
                  "devDependencies": {
                    "@playwright/test": "1"
                  }
                }
                """,
            )
            write(
                root / "apps" / "web" / "tests" / "home.spec.ts",
                """
                test("home", async ({ page }) => {
                  await page.goto("/")
                })
                """,
            )
            write(
                root / "services" / "api" / "pyproject.toml",
                """
                [project]
                dependencies = ["fastapi", "pytest"]
                """,
            )
            write(
                root / "services" / "api" / "tests" / "users_test.py",
                """
                def test_users(client):
                    assert client.get("/api/users").status_code == 200
                """,
            )
            report = json.loads(
                run_script(
                    "discover_product.py",
                    "--source",
                    f"product={root}",
                ).stdout
            )
            self.assertEqual(
                {component["path"] for component in report["components"]},
                {"apps/web", "services/api"},
            )

    def test_mixed_repository_keeps_all_surfaces(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write(
                root / "package.json",
                """
                {
                  "dependencies": {
                    "express": "1",
                    "commander": "1",
                    "bullmq": "1",
                    "react-native": "1"
                  }
                }
                """,
            )
            write(
                root / "tests" / "worker.test.ts",
                """
                test("job", async () => {
                  await enqueue("job")
                })
                """,
            )
            result = run_script(
                "discover_product.py",
                "--source",
                f"product={root}",
                "--output-dir",
                str(root / "playbook-output"),
            )
            report = json.loads(result.stdout)
            repository = report["repositories"][0]
            self.assertEqual(repository["source_id"], "product")
            self.assertEqual(
                set(repository["surfaces"]),
                {"api", "cli", "mobile", "service", "worker"},
            )
            self.assertEqual(
                set(report["components"][0]["surfaces"]),
                {"api", "cli", "mobile", "service", "worker"},
            )

    def test_unknown_toolchain_still_finds_tests_and_commands(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write(root / "Makefile", "test:\n\tzig build test\n")
            write(root / "tests" / "journey.zig", 'test "journey" {}\n')
            report = json.loads(
                run_script(
                    "discover_product.py",
                    "--source",
                    f"engine={root}",
                    "--test-framework",
                    "zig-test",
                    "--output-dir",
                    str(root / "playbook-output"),
                ).stdout
            )
            repository = report["repositories"][0]
            self.assertEqual(repository["languages"], ["zig"])
            self.assertEqual(repository["test_files"], ["tests/journey.zig"])
            self.assertEqual(repository["test_commands"]["make-test"], "make test")
            self.assertEqual(report["components"][0]["frameworks"], ["zig-test"])

    def test_remote_repository_is_acquired_into_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            remote = root / "remote"
            remote.mkdir()
            subprocess.run(["git", "init", str(remote)], check=True, capture_output=True)
            write(remote / "Makefile", "test:\n\ttrue\n")
            subprocess.run(["git", "-C", str(remote), "add", "Makefile"], check=True)
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(remote),
                    "-c",
                    "user.name=Fixture",
                    "-c",
                    "user.email=fixture@example.invalid",
                    "commit",
                    "-m",
                    "fixture",
                ],
                check=True,
                capture_output=True,
            )
            revision = subprocess.run(
                ["git", "-C", str(remote), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            workspace = root / "checkouts"
            report = json.loads(
                run_script(
                    "bootstrap_playbook.py",
                    "--source",
                    f"remote=file://{remote}",
                    "--source-ref",
                    f"remote={revision}",
                    "--workspace-dir",
                    str(workspace),
                ).stdout
            )
            source = report["sources"][0]
            self.assertEqual(source["source_id"], "remote")
            self.assertEqual(source["locator_type"], "remote")
            self.assertEqual(source["revision"], revision)
            self.assertTrue(source["cleanup_required"])
            self.assertTrue((Path(source["root"]) / "Makefile").is_file())
            self.assertTrue(report["ask_before_write"])

    def test_bootstrap_without_arguments_inspects_cwd_and_requires_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write(root / "Makefile", "test:\n\tpython -m unittest\n")
            report = json.loads(
                run_script(
                    "bootstrap_playbook.py",
                    cwd=root,
                ).stdout
            )
            self.assertTrue(
                report["intake"]["defaulted_source_to_current_directory"]
            )
            self.assertTrue(report["intake"]["requires_user_confirmation"])
            self.assertFalse(report["bootstrap"]["ready"])
            self.assertEqual(
                report["bootstrap"]["next_action"],
                "present_findings_and_confirm",
            )
            self.assertEqual(
                Path(report["sources"][0]["root"]),
                root.resolve(),
            )
            question_ids = {
                question["id"] for question in report["intake"]["questions"]
            }
            self.assertIn("confirm_source_addresses", question_ids)
            self.assertIn("confirm_source_roles", question_ids)
            self.assertIn("choose_action", question_ids)

            explicit = json.loads(
                run_script(
                    "bootstrap_playbook.py",
                    "--intent",
                    "create",
                    cwd=root,
                ).stdout
            )
            self.assertFalse(explicit["intake"]["requires_user_confirmation"])
            self.assertTrue(explicit["bootstrap"]["ready"])
            self.assertEqual(
                explicit["bootstrap"]["next_action"],
                "analyze_then_create",
            )

    def test_git_remote_addresses_are_reported_without_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(["git", "init", str(root)], check=True, capture_output=True)
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(root),
                    "remote",
                    "add",
                    "origin",
                    "https://user:secret@example.com/org/repo.git?token=secret",
                ],
                check=True,
                capture_output=True,
            )
            write(root / "README.md", "# Product\n")
            report = json.loads(
                run_script(
                    "discover_product.py",
                    "--source",
                    f"product={root}",
                ).stdout
            )
            identity = report["repositories"][0]["repository_identity"]
            self.assertEqual(identity["git_root"], str(root.resolve()))
            self.assertEqual(
                identity["remotes"][0]["fetch_url"],
                "https://example.com/org/repo.git",
            )
            self.assertNotIn("secret", json.dumps(report))

    def test_nested_repository_is_reported_with_an_assumed_role(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            nested = root / "product-docs"
            subprocess.run(["git", "init", str(root)], check=True, capture_output=True)
            subprocess.run(["git", "init", str(nested)], check=True, capture_output=True)
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(nested),
                    "remote",
                    "add",
                    "origin",
                    "https://example.test/product/docs.git",
                ],
                check=True,
                capture_output=True,
            )
            write(root / "README.md", "# Wrapper\n")
            write(nested / "README.md", "# Documentation\n")
            make_playbook(nested / "docs" / "playbook")
            report = json.loads(
                run_script(
                    "discover_product.py",
                    "--source",
                    f"product={root}",
                ).stdout
            )
            candidates = report["repositories"][0][
                "linked_repository_candidates"
            ]
            self.assertEqual(len(candidates), 1)
            self.assertEqual(candidates[0]["path"], "product-docs")
            self.assertIn("docs", candidates[0]["assumed_roles"])
            self.assertEqual(
                candidates[0]["remotes"][0]["fetch_url"],
                "https://example.test/product/docs.git",
            )
            self.assertEqual(len(candidates[0]["playbook_candidates"]), 1)
            self.assertEqual(report["output_decision"], "confirm_linked_draft")
            self.assertTrue(report["ask_before_write"])
            self.assertEqual(
                report["continuation_suggestion"],
                "confirm_and_continue_linked_playbook",
            )

    def test_contract_addresses_docs_and_prior_work_are_discovered(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write(
                root / "package.json",
                """
                {
                  "dependencies": {
                    "react": "19"
                  }
                }
                """,
            )
            write(
                root / "cache" / "openapi.json",
                """
                {
                  "openapi": "3.1.0",
                  "info": {"title": "Fixture API", "version": "2"},
                  "servers": [{"url": "https://api.example.test/v2?token=hidden"}],
                  "paths": {
                    "/accounts": {
                      "get": {
                        "tags": ["accounts"],
                        "responses": {"200": {"description": "ok"}}
                      }
                    }
                  }
                }
                """,
            )
            write(
                root / "README.md",
                """
                # Web

                Development API: http://localhost:4010
                Configure `VITE_API_BASE_URL`.
                """,
            )
            write(
                root / "API Scenarios" / "README.md",
                "# API scenario catalog\n",
            )
            playbook = root / "docs" / "playbook"
            make_playbook(playbook)
            write(
                playbook / ".product-playbook-state.json",
                """
                {
                  "managed_by": "product-playbook",
                  "schema_version": 3,
                  "sources": {"web": {}},
                  "scenarios": {"ACC-01": {}}
                }
                """,
            )
            report = json.loads(
                run_script(
                    "discover_product.py",
                    "--source",
                    f"web={root}",
                ).stdout
            )
            repository = report["repositories"][0]
            contract = repository["contract_evidence"][0]
            self.assertEqual(contract["path"], "cache/openapi.json")
            self.assertEqual(contract["role"], "cached-or-generated")
            self.assertEqual(
                contract["repository_context"],
                "frontend-contract-copy-or-codegen-input",
            )
            self.assertEqual(contract["summary"]["path_count"], 1)
            addresses = {
                item["value"] for item in repository["address_candidates"]
            }
            self.assertIn("http://localhost:4010", addresses)
            self.assertIn("https://api.example.test/v2", addresses)
            self.assertIn("VITE_API_BASE_URL", addresses)
            docs = {
                item["path"] for item in repository["documentation_candidates"]
            }
            self.assertIn("API Scenarios/README.md", docs)
            self.assertEqual(
                report["existing_playbook_candidates"][0]["state"]["managed_by"],
                "product-playbook",
            )
            self.assertEqual(
                report["continuation_suggestion"],
                "continue_unique_playbook",
            )
            self.assertNotIn("hidden", json.dumps(report))

    def test_rag_and_helper_packages_are_kept_as_distinct_surfaces(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write(
                root / "services" / "rag" / "pyproject.toml",
                """
                [project]
                dependencies = ["langchain", "qdrant-client"]
                """,
            )
            write(
                root / "services" / "rag" / "app" / "retrieval.py",
                "def retrieve_context(query):\n    return vector_store.search(query)\n",
            )
            write(
                root / "packages" / "helpers" / "package.json",
                """
                {
                  "name": "helpers",
                  "exports": {".": "./index.js"},
                  "types": "./index.d.ts"
                }
                """,
            )
            write(
                root / "packages" / "helpers" / "index.js",
                "export const normalize = value => value\n",
            )
            report = json.loads(
                run_script(
                    "discover_product.py",
                    "--source",
                    f"product={root}",
                    "--output-dir",
                    str(root / "playbook-output"),
                ).stdout
            )
            components = {
                component["path"]: set(component["surfaces"])
                for component in report["components"]
            }
            self.assertIn("rag", components["services/rag"])
            self.assertIn("library", components["packages/helpers"])


class StateAndValidationTests(unittest.TestCase):
    def test_renderer_creates_a_valid_playbook(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plan = root / "plan.json"
            output = root / "playbook"
            write(
                plan,
                """
                {
                  "title": "Account Playbook",
                  "purpose": "Validate account journeys.",
                  "actors": ["Tester"],
                  "interfaces": ["Use the supported API client."],
                  "chapters": [
                    {
                      "title": "Accounts",
                      "scenarios": [
                        {
                          "id": "ACC-01",
                          "title": "Complete email verification",
                          "goal": "List available accounts.",
                          "who": "Tester",
                          "steps": ["Send `GET /api/accounts`."],
                          "expected": ["The response status is `200`."]
                        }
                      ]
                    }
                  ]
                }
                """,
            )
            render = json.loads(
                run_script("render_playbook.py", str(plan), str(output)).stdout
            )
            self.assertEqual(render["scenarios"], 1)
            validation = json.loads(
                run_script(
                    "validate_playbook.py",
                    str(output),
                    "--json",
                ).stdout
            )
            self.assertTrue(validation["valid"])

    def test_portable_state_and_strict_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "api"
            playbook = root / "playbook"
            make_playbook(playbook)
            write(
                source / "tests" / "accounts_test.py",
                """
                def test_accounts(client):
                    response = client.get("/api/accounts")
                    assert response.status_code == 200
                """,
            )
            ledger = root / "ledger.json"
            write(
                ledger,
                """
                {
                  "scenarios": {
                    "ACC-01": {
                      "status": "SOURCED",
                      "sources": [
                        {
                          "source_id": "api",
                          "path": "tests/accounts_test.py"
                        }
                      ]
                    }
                  }
                }
                """,
            )
            state_report = json.loads(
                run_script(
                    "inventory_playbook.py",
                    str(playbook),
                    "--source",
                    f"api={source}",
                    "--evidence-ledger",
                    str(ledger),
                    "--write-state",
                ).stdout
            )
            self.assertTrue(state_report["state_written"])
            state_path = playbook / ".product-playbook-state.json"
            portable_state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(portable_state["managed_by"], "product-playbook")
            scenario_state = portable_state["scenarios"]["ACC-01"]
            self.assertEqual(
                scenario_state["sources"][0]["path"],
                "tests/accounts_test.py",
            )
            self.assertNotIn(str(source), json.dumps(scenario_state))
            self.assertNotIn("status", scenario_state)
            self.assertNotIn("generated_at", portable_state)
            self.assertFalse((playbook / ".product-playbook").exists())
            self.assertEqual(
                [
                    path.name
                    for path in playbook.iterdir()
                    if path.is_file() and path.suffix != ".md"
                ],
                [".product-playbook-state.json"],
            )

            validation = json.loads(
                run_script(
                    "validate_playbook.py",
                    str(playbook),
                    "--json",
                    "--require-state",
                ).stdout
            )
            self.assertTrue(validation["valid"])

            web = root / "web"
            write(
                web / "e2e" / "accounts.spec.ts",
                """
                test("accounts", async ({ page }) => {
                  await page.goto("/accounts")
                })
                """,
            )
            web_ledger = root / "web-ledger.json"
            write(
                web_ledger,
                """
                {
                  "scenarios": {
                    "ACC-01": {
                      "status": "SOURCED",
                      "sources": [
                        {
                          "source_id": "web",
                          "path": "e2e/accounts.spec.ts"
                        }
                      ]
                    }
                  }
                }
                """,
            )
            run_script(
                "inventory_playbook.py",
                str(playbook),
                "--source",
                f"web={web}",
                "--run-scope",
                "contribution",
                "--scope",
                "web",
                "--evidence-ledger",
                str(web_ledger),
                "--base-state-digest",
                state_report["state_digest"],
                "--write-state",
            )
            contributed_state = json.loads(
                state_path.read_text(encoding="utf-8")
            )["scenarios"]["ACC-01"]
            self.assertEqual(
                {item["source_id"] for item in contributed_state["sources"]},
                {"api", "web"},
            )
            stale = run_script(
                "inventory_playbook.py",
                str(playbook),
                "--source",
                f"web={web}",
                "--run-scope",
                "contribution",
                "--scope",
                "web",
                "--evidence-ledger",
                str(web_ledger),
                "--base-state-digest",
                state_report["state_digest"],
                "--write-state",
                check=False,
            )
            self.assertNotEqual(stale.returncode, 0)
            self.assertIn("state changed after analysis", stale.stderr)

            leaked_state = json.loads(state_path.read_text(encoding="utf-8"))
            leaked_state["scenarios"]["ACC-01"]["status"] = "SOURCED"
            state_path.write_text(
                json.dumps(leaked_state, indent=2) + "\n",
                encoding="utf-8",
            )
            leaked_validation = run_script(
                "validate_playbook.py",
                str(playbook),
                "--json",
                "--require-state",
                check=False,
            )
            leaked_codes = {
                item["code"]
                for item in json.loads(leaked_validation.stdout)["errors"]
            }
            self.assertIn("authoring-meta-in-state", leaked_codes)

    def test_legacy_state_migrates_to_one_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            playbook = Path(temporary)
            make_playbook(playbook)
            legacy = playbook / ".product-playbook"
            write(
                playbook / ".product-playbook-state.json",
                """
                {
                  "schema_version": 1,
                  "generated_at": "legacy timestamp",
                  "draft_digest": "old-draft",
                  "roots": {
                    "code0": {
                      "path": "/old/machine/path"
                    }
                  },
                  "scenarios": {
                    "ACC-01": {
                      "title": "List accounts",
                      "body_hash": "old-scenario-digest",
                      "status": "SOURCED",
                      "sources": []
                    }
                  }
                }
                """,
            )
            write(
                legacy / "manifest.json",
                """
                {
                  "schema_version": 2,
                  "draft_digest": "legacy",
                  "run_scope": "full",
                  "source_ids": ["api"],
                  "scenario_ids": ["ACC-01"],
                  "state_digest": "legacy-digest"
                }
                """,
            )
            write(
                legacy / "sources" / "api.json",
                """
                {
                  "source_id": "api",
                  "kind": "code",
                  "revision": null,
                  "dirty": false,
                  "fingerprint": {
                    "digest": "source-digest",
                    "file_count": 1
                  }
                }
                """,
            )
            write(
                legacy / "scenarios" / "ACC-01.json",
                """
                {
                  "title": "List accounts",
                  "body_hash": "scenario-digest",
                  "sources": [
                    {
                      "source_id": "api",
                      "path": "tests/accounts_test.py",
                      "sha256": "evidence-digest"
                    }
                  ]
                }
                """,
            )

            report = json.loads(
                run_script(
                    "inventory_playbook.py",
                    str(playbook),
                    "--migrate-state",
                ).stdout
            )
            self.assertTrue(report["state_migrated"])
            self.assertFalse(legacy.exists())
            state_path = playbook / ".product-playbook-state.json"
            self.assertTrue(state_path.is_file())
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(state["schema_version"], 3)
            self.assertEqual(state["managed_by"], "product-playbook")
            self.assertNotIn("generated_at", state)
            self.assertNotIn("/old/machine/path", json.dumps(state))
            self.assertEqual(
                state["scenarios"]["ACC-01"]["sources"][0]["path"],
                "tests/accounts_test.py",
            )

            validation = json.loads(
                run_script(
                    "validate_playbook.py",
                    str(playbook),
                    "--json",
                    "--require-state",
                ).stdout
            )
            self.assertTrue(validation["valid"])

    def test_migration_refuses_unrecognized_legacy_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            playbook = Path(temporary)
            make_playbook(playbook)
            legacy = playbook / ".product-playbook"
            write(
                legacy / "manifest.json",
                """
                {
                  "schema_version": 2,
                  "source_ids": [],
                  "scenario_ids": []
                }
                """,
            )
            write(legacy / "keep-me.txt", "not owned by the skill\n")

            result = run_script(
                "inventory_playbook.py",
                str(playbook),
                "--migrate-state",
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unexpected file", result.stderr)
            self.assertTrue((legacy / "keep-me.txt").is_file())
            self.assertFalse((playbook / ".product-playbook-state.json").exists())

    def test_validator_rejects_checklist_and_punctuation_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            playbook = Path(temporary)
            make_playbook(playbook)
            chapter = playbook / "01-account.md"
            chapter.write_text(
                chapter.read_text(encoding="utf-8")
                .replace("ACC-01\n```", "ACC-99\n```")
                .replace("List available accounts.", "List accounts; then review them."),
                encoding="utf-8",
            )
            result = run_script(
                "validate_playbook.py",
                str(playbook),
                "--json",
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            codes = {item["code"] for item in json.loads(result.stdout)["errors"]}
            self.assertIn("checklist-mismatch", codes)
            self.assertIn("forbidden-punctuation", codes)

    def test_validator_rejects_authoring_history_and_prior_results(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            playbook = Path(temporary)
            make_playbook(playbook)
            readme = playbook / "README.md"
            readme.write_text(
                readme.read_text(encoding="utf-8")
                + "\n## Change history\n\n- Updated after source review.\n"
                + "\n<!-- SOURCED from an internal test -->\n",
                encoding="utf-8",
            )
            results = playbook / "results-template.md"
            results.write_text(
                results.read_text(encoding="utf-8").replace(
                    "| ACC-01 | |",
                    "| ACC-01 | P |",
                ),
                encoding="utf-8",
            )
            result = run_script(
                "validate_playbook.py",
                str(playbook),
                "--json",
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            codes = {item["code"] for item in json.loads(result.stdout)["errors"]}
            self.assertIn("forbidden-authoring-meta", codes)
            self.assertIn("hidden-authoring-meta", codes)
            self.assertIn("prepopulated-result", codes)


class HtmlExportTests(unittest.TestCase):
    """Opt-in single-file export. Markdown stays the default output.

    PDF conversion needs an external binary (Chrome / wkhtmltopdf / pandoc) that
    CI cannot guarantee, so PDF-mode is tested only for its no-converter failure
    path and a converter-gated happy path. HTML-mode is deterministic and fully
    covered since it is pure standard library.
    """

    def _two_chapter_plan(self, root: Path) -> Path:
        plan = root / "plan.json"
        write(
            plan,
            """
            {
              "title": "Account Playbook",
              "purpose": "Validate account and billing journeys.",
              "actors": ["Tester"],
              "interfaces": ["Use the supported API client."],
              "chapters": [
                {
                  "title": "Accounts",
                  "scenarios": [
                    {
                      "id": "ACC-01",
                      "title": "List accounts",
                      "goal": "List available accounts.",
                      "who": "Tester",
                      "steps": ["Send `GET /api/accounts`."],
                      "expected": ["The response status is `200`."]
                    }
                  ]
                },
                {
                  "title": "Billing",
                  "scenarios": [
                    {
                      "id": "BIL-01",
                      "title": "View invoice",
                      "goal": "View the current invoice.",
                      "who": "Tester",
                      "steps": ["Open the <billing> page for A & B."],
                      "expected": ["The invoice renders correctly."]
                    }
                  ]
                }
              ]
            }
            """,
        )
        return plan

    def test_html_export_produces_self_contained_file_in_order(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            playbook = root / "playbook"
            plan = self._two_chapter_plan(root)
            render = json.loads(
                run_script("render_playbook.py", str(plan), str(playbook)).stdout
            )
            self.assertEqual(render["scenarios"], 2)

            export = json.loads(
                run_script("export_playbook.py", str(playbook), "--format", "html").stdout
            )
            self.assertEqual(export["format"], "html")
            self.assertTrue(export["intermediate_html_kept"])
            self.assertEqual(export["chapters"], 2)
            self.assertEqual(export["scenarios"], 2)
            self.assertEqual(export["files"], [
                "README.md",
                "01-accounts.md",
                "02-billing.md",
                "results-template.md",
            ])
            html_path = playbook / "playbook.html"
            self.assertTrue(html_path.is_file())
            # HTML mode must not produce a PDF.
            self.assertFalse((playbook / "playbook.pdf").exists())
            body = html_path.read_text(encoding="utf-8")

            # Inline CSS, no external assets, no scripts.
            self.assertIn("<style>", body)
            self.assertNotIn("<script", body)
            self.assertNotIn(" src=\"", body)
            # Required content from every section.
            self.assertIn("Account Playbook", body)
            self.assertIn("Accounts", body)
            self.assertIn("Billing", body)
            self.assertIn("Results", body)
            self.assertIn("ACC-01", body)
            # Scenario bodies are wrapped for indentation.
            self.assertIn('class="scenario-body"', body)
            # Sections appear in tester-facing order. Assert on section anchors
            # rather than substrings, because the README cross-references every
            # scenario ID and the results template in its map and full-pass list.
            self.assertLess(body.index('id="readme"'), body.index('id="01-accounts"'))
            self.assertLess(body.index('id="01-accounts"'), body.index('id="02-billing"'))
            self.assertLess(body.index('id="02-billing"'), body.index('id="results-template"'))

    def test_html_export_excludes_state_and_non_markdown_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            playbook = root / "playbook"
            plan = self._two_chapter_plan(root)
            run_script("render_playbook.py", str(plan), str(playbook))
            write(
                playbook / ".product-playbook-state.json",
                """
                {
                  "managed_by": "product-playbook",
                  "scenarios": {"ACC-01": {"sources": [{"path": "secret/evidence.py"}]}}
                }
                """,
            )
            write(playbook / "notes.txt", "SECRET-LEAK should not appear\n")

            run_script("export_playbook.py", str(playbook), "--format", "html")
            body = (playbook / "playbook.html").read_text(encoding="utf-8")
            self.assertNotIn("SECRET-LEAK", body)
            self.assertNotIn("product-playbook", body)
            self.assertNotIn("secret/evidence.py", body)

    def test_html_export_escapes_inline_angle_brackets_and_ampersand(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            playbook = root / "playbook"
            plan = self._two_chapter_plan(root)
            run_script("render_playbook.py", str(plan), str(playbook))
            run_script("export_playbook.py", str(playbook), "--format", "html")
            body = (playbook / "playbook.html").read_text(encoding="utf-8")
            # The literal <billing> from the step must be escaped, never a raw tag.
            self.assertIn("&lt;billing&gt;", body)
            self.assertNotIn("<billing>", body)
            # The ampersand must be escaped too.
            self.assertIn("A &amp; B", body)

    def test_html_export_rewrites_internal_links_to_anchors(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            playbook = root / "playbook"
            plan = self._two_chapter_plan(root)
            run_script("render_playbook.py", str(plan), str(playbook))
            run_script("export_playbook.py", str(playbook), "--format", "html")
            body = (playbook / "playbook.html").read_text(encoding="utf-8")
            self.assertIn('href="#02-billing"', body)
            self.assertIn('href="#results-template"', body)
            self.assertNotIn('href="02-billing.md"', body)

    def test_html_export_refuses_overwrite_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            playbook = root / "playbook"
            plan = self._two_chapter_plan(root)
            run_script("render_playbook.py", str(plan), str(playbook))
            run_script("export_playbook.py", str(playbook), "--format", "html")
            html_path = playbook / "playbook.html"
            first_mtime = html_path.stat().st_mtime_ns

            refused = run_script(
                "export_playbook.py", str(playbook), "--format", "html", check=False
            )
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn("already exists", refused.stderr)
            self.assertEqual(html_path.stat().st_mtime_ns, first_mtime)

            forced = run_script(
                "export_playbook.py", str(playbook), "--format", "html", "--force"
            )
            self.assertEqual(forced.returncode, 0)

    def test_export_fails_when_required_files_are_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            playbook = root / "playbook"
            playbook.mkdir()
            write(playbook / "01-lone.md", "# Lone chapter\n")
            result = run_script(
                "export_playbook.py", str(playbook), "--format", "html", check=False
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("README.md", result.stderr)

    def test_html_export_counts_only_scenario_headings_not_cross_references(self) -> None:
        # A loose ID mention in another chapter's prose (e.g. "Continue from
        # ACC-01") must not inflate the scenario count. Only "## ID: Title"
        # headings count, matching the renderer and the validator.
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            playbook = root / "playbook"
            playbook.mkdir()
            write(
                playbook / "README.md",
                """
                # Playbook

                ## Playbook map
                - [Account](01-account.md)
                - [Order](02-order.md)

                ## Smoke path
                Run ACC-01.

                ## Full pass
                Run ACC-01.

                ## Sign-off
                Sign off.
                """,
            )
            write(
                playbook / "01-account.md",
                """
                # Account

                ## Scenario list
                | ID | Scenario | Persona |
                | --- | --- | --- |
                | ACC-01 | Sign in | Tester |

                ## ACC-01: Sign in

                **Goal**

                Sign in.

                **Who**

                Tester.

                **Steps**

                1. Open the page.

                **Expected**

                - Dashboard shows.

                ## Chapter checklist

                ```text
                ACC-01
                ```

                [Continue](02-order.md)
                """,
            )
            write(
                playbook / "02-order.md",
                """
                # Order

                ## Scenario list
                | ID | Scenario | Persona |
                | --- | --- | --- |
                | ORD-01 | Find order | Tester |

                ## ORD-01: Find order

                **Goal**

                Find the order placed in ACC-01.

                **Who**

                Tester.

                **Steps**

                1. Enter the order from ACC-01.

                **Expected**

                - Order shows.

                ## Chapter checklist

                ```text
                ORD-01
                ```

                [Results](results-template.md)
                """,
            )
            write(
                playbook / "results-template.md",
                """
                # Results

                ## Legend
                Use P, F, B, or N.

                ## Summary
                Summarize.
                """,
            )
            export = json.loads(
                run_script("export_playbook.py", str(playbook), "--format", "html").stdout
            )
            self.assertEqual(export["scenarios"], 2)

    def test_pdf_export_fails_clearly_when_no_converter_available(self) -> None:
        # When no PDF converter is installed, --format pdf must fail with a clear
        # message and must not leave an HTML file behind in the output directory.
        if _any_pdf_converter_available():
            self.skipTest("a PDF converter is installed; the no-converter path cannot run")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            playbook = root / "playbook"
            plan = self._two_chapter_plan(root)
            run_script("render_playbook.py", str(plan), str(playbook))
            result = run_script(
                "export_playbook.py", str(playbook), "--format", "pdf", check=False
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("no PDF converter found", result.stderr)
            # No intermediate HTML leaked into the playbook directory.
            self.assertFalse((playbook / "playbook.html").exists())
            self.assertFalse((playbook / "playbook.pdf").exists())

    def test_pdf_export_produces_pdf_and_removes_intermediate_html(self) -> None:
        # When a converter is present, --format pdf writes playbook.pdf and the
        # intermediate HTML is deleted. Skipped in CI without a converter.
        if not _any_pdf_converter_available():
            self.skipTest("no PDF converter installed")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            playbook = root / "playbook"
            plan = self._two_chapter_plan(root)
            run_script("render_playbook.py", str(plan), str(playbook))
            export = json.loads(
                run_script("export_playbook.py", str(playbook), "--format", "pdf").stdout
            )
            self.assertEqual(export["format"], "pdf")
            self.assertFalse(export["intermediate_html_kept"])
            pdf_path = playbook / "playbook.pdf"
            self.assertTrue(pdf_path.is_file())
            self.assertEqual(pdf_path.read_bytes()[:4], b"%PDF")
            # The intermediate HTML must be gone.
            self.assertFalse((playbook / "playbook.html").exists())


def _any_pdf_converter_available() -> bool:
    """True when a PDF converter this script can drive is installed."""
    import shutil as _shutil
    from pathlib import Path as _Path
    chrome_candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    ]
    if any(_Path(c).is_file() for c in chrome_candidates):
        return True
    return any(_shutil.which(n) for n in ("chromium", "chromium-browser", "google-chrome", "chrome", "wkhtmltopdf", "pandoc"))


if __name__ == "__main__":
    unittest.main()
