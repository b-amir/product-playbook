#!/usr/bin/env python3
"""Check, run, report, and drift-check runnable tests generated next to a playbook.

Generated tests live in a sibling folder (default ``<playbook-parent>/playbook-tests/``)
described by one config file, ``playbook-tests.json``. The playbook folder itself stays
Markdown plus state. Stdlib only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

CONFIG_NAME = "playbook-tests.json"
MANAGED_BY = "product-playbook"
SCENARIO_ID = re.compile(r"^[A-Z][A-Z0-9]{1,5}-\d{2,3}$")
ACCEPTANCE_ID = re.compile(r"\b(EX-[0-9A-Za-z.\-]+[0-9A-Za-z])\b")
TAGS = {"smoke", "safe", "destructive"}
TARGET_KINDS = {"local", "dev", "staging", "prod", "custom"}
PROD_DEFAULT_TAGS = {"smoke", "safe"}
SECRET_KEY = re.compile(r"(pass(word)?|secret|token|api[_-]?key|cookie|credential|auth)", re.I)
URL_WITH_USERINFO = re.compile(r"^[a-z][a-z0-9+.-]*://[^/@\s]+:[^/@\s]*@", re.I)
ENV_NAME = re.compile(r"^[A-Z_][A-Z0-9_]*$")
SYMBOL = {"pass": "P", "fail": "F", "blocked": "B", "env": "E", "unbuilt": "U", "na": "N"}
LABEL = {
    "pass": "Pass",
    "fail": "Fail",
    "blocked": "Blocked",
    "env": "Blocked (environment)",
    "unbuilt": "Not built yet",
    "na": "Not run",
}
NOT_OK = {"fail", "blocked", "env", "unbuilt"}
DEFAULT_TICKET = re.compile(r"\b[A-Z][A-Z0-9]{1,9}-\d+\b")
HISTORY_DIR = "playbook-runs"
CAPABILITY = re.compile(r"^[a-z][a-z0-9-]*$")
# A test that cannot run because the environment lacks something prints this marker
# (for pytest: pytest.skip("[env] needs s3: ...")). It is reported as E, not B or F.
ENV_MARKER = re.compile(r"\[env\]\s*([^\n]*)")
# A test that finds the feature missing (route absent, flag off) prints "[not-built] ...".
NOT_BUILT_MARKER = re.compile(r"\[not-built\]\s*([^\n]*)")


# ---------------------------------------------------------------- config


def config_path(tests_dir: Path) -> Path:
    return tests_dir / CONFIG_NAME


def load_config(tests_dir: Path) -> dict[str, Any]:
    path = config_path(tests_dir)
    if not path.is_file():
        raise ValueError(f"missing {CONFIG_NAME} in {tests_dir}")
    return json.loads(path.read_text(encoding="utf-8"))


def save_config(tests_dir: Path, config: dict[str, Any]) -> None:
    config_path(tests_dir).write_text(
        json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def walk(value: Any, prefix: str = "") -> list[tuple[str, Any]]:
    items: list[tuple[str, Any]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            items.append((path, child))
            items.extend(walk(child, path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            items.extend(walk(child, f"{prefix}[{index}]"))
    return items


def check_config(
    config: dict[str, Any],
    tests_dir: Path | None = None,
    playbook_ids: set[str] | None = None,
) -> list[str]:
    """Return a list of human-readable errors. Empty means valid."""
    errors: list[str] = []
    if config.get("managed_by") != MANAGED_BY:
        errors.append(f"managed_by must be {MANAGED_BY!r}")
    targets = config.get("targets")
    if not isinstance(targets, dict) or not targets:
        errors.append("targets must be a non-empty object")
        targets = {}
    for name, target in targets.items():
        if not isinstance(target, dict):
            errors.append(f"target {name} must be an object")
            continue
        if target.get("kind") not in TARGET_KINDS:
            errors.append(f"target {name} kind must be one of {sorted(TARGET_KINDS)}")
        if not (target.get("base_url") or target.get("base_url_env")):
            errors.append(f"target {name} needs base_url or base_url_env")
        if target.get("kind") == "prod" and target.get("base_url"):
            errors.append(f"target {name} is prod: use base_url_env, not a literal URL")
        env_name = target.get("base_url_env")
        if env_name and not ENV_NAME.match(str(env_name)):
            errors.append(f"target {name} base_url_env must be an env var name")
        provides = target.get("provides", [])
        if not isinstance(provides, list):
            errors.append(f"target {name} provides must be a list of capability names")
        else:
            for cap in provides:
                errors.extend(capability_errors(config, f"target {name} provides", cap))
    default = config.get("default_target")
    if default and default not in targets:
        errors.append(f"default_target {default!r} is not a target")
    tickets = config.get("tickets", {})
    if not isinstance(tickets, dict):
        errors.append("tickets must be an object")
    else:
        if tickets.get("pattern"):
            try:
                re.compile(str(tickets["pattern"]))
            except re.error:
                errors.append("tickets.pattern is not a valid regular expression")
        for key in ("ready_states",):
            if key in tickets and not (
                isinstance(tickets[key], list) and all(isinstance(x, str) for x in tickets[key])
            ):
                errors.append(f"tickets.{key} must be a list of state names")
    history = config.get("history_dir", HISTORY_DIR)
    if not isinstance(history, str) or Path(history).is_absolute() or ".." in Path(history).parts:
        errors.append("history_dir must be a relative folder inside the tests folder")
    for name in config.get("credentials_env", []) or []:
        if not ENV_NAME.match(str(name)):
            errors.append(f"credentials_env entry {name!r} must be an env var name")

    # Credentials only ever by env var name.
    for path, value in walk(config):
        key = path.rsplit(".", 1)[-1].split("[", 1)[0]
        if isinstance(value, str) and URL_WITH_USERINFO.match(value):
            errors.append(f"{path} embeds credentials in a URL")
        if (
            SECRET_KEY.search(key)
            and not key.endswith("_env")
            and key not in {"credentials_env"}
            and isinstance(value, (str, int))
            and not path.startswith("acceptance.")
            and ".title" not in path
        ):
            errors.append(f"{path} looks like a literal credential; reference an env var name")

    scenarios = config.get("scenarios")
    if not isinstance(scenarios, dict) or not scenarios:
        errors.append("scenarios must be a non-empty object keyed by scenario ID")
        scenarios = {}
    acceptance = config.get("acceptance", {}) or {}
    for scenario_id, entry in scenarios.items():
        if not SCENARIO_ID.match(scenario_id):
            errors.append(f"bad scenario ID {scenario_id}")
        if playbook_ids is not None and scenario_id not in playbook_ids:
            errors.append(f"{scenario_id} is not a scenario in the playbook")
        if not isinstance(entry, dict):
            errors.append(f"{scenario_id} must be an object")
            continue
        for ref in entry.get("acceptance", []) or []:
            if ref not in acceptance:
                errors.append(f"{scenario_id} maps unknown acceptance example {ref}")
        if entry.get("manual_only"):
            if not entry.get("reason"):
                errors.append(f"{scenario_id} is manual_only and needs a reason")
            continue
        linked = entry.get("tickets", [])
        if not isinstance(linked, list) or not all(isinstance(x, str) and x for x in linked):
            errors.append(f"{scenario_id} tickets must be a list of ticket references")
        for item in entry.get("readiness", []) or []:
            if not isinstance(item, dict) or not item.get("source_id") or not item.get("path"):
                errors.append(f"{scenario_id} readiness items need source_id and path")
            elif Path(item["path"]).is_absolute() or ".." in Path(item["path"]).parts:
                errors.append(f"{scenario_id} readiness path must be source-relative")
            elif item.get("contains"):
                try:
                    re.compile(item["contains"])
                except re.error:
                    errors.append(f"{scenario_id} readiness contains is not a valid regex")
        requires = entry.get("requires", [])
        if not isinstance(requires, list):
            errors.append(f"{scenario_id} requires must be a list of capability names")
        else:
            for cap in requires:
                errors.extend(capability_errors(config, f"{scenario_id} requires", cap))
        tags = set(entry.get("tags", []) or [])
        if not tags or not tags <= TAGS:
            errors.append(f"{scenario_id} tags must be a non-empty subset of {sorted(TAGS)}")
        if "safe" in tags and "destructive" in tags:
            errors.append(f"{scenario_id} cannot be both safe and destructive")
        run = entry.get("run")
        if not isinstance(run, list) or not run or not all(isinstance(x, str) for x in run):
            errors.append(f"{scenario_id} run must be a non-empty argv list")
        if not entry.get("test"):
            errors.append(f"{scenario_id} needs test (relative test file path)")
        elif tests_dir is not None and not (tests_dir / entry["test"]).is_file():
            errors.append(f"{scenario_id} test file missing: {entry['test']}")
        evidence = entry.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            errors.append(f"{scenario_id} needs evidence (no evidence, no automation)")
        else:
            for item in evidence:
                if not isinstance(item, dict) or not item.get("source_id") or not item.get("path"):
                    errors.append(f"{scenario_id} evidence items need source_id and path")
                elif Path(item["path"]).is_absolute() or ".." in Path(item["path"]).parts:
                    errors.append(f"{scenario_id} evidence path must be source-relative")
    return errors


def capability_errors(config: dict[str, Any], where: str, cap: Any) -> list[str]:
    if not isinstance(cap, str) or not CAPABILITY.match(cap):
        return [f"{where}: bad capability name {cap!r} (lowercase, digits, dashes)"]
    declared = config.get("capabilities")
    if isinstance(declared, dict) and declared and cap not in declared:
        return [f"{where}: capability {cap!r} is not declared in capabilities"]
    return []


def target_provides(config: dict[str, Any], name: str, extra: set[str] | None = None) -> set[str]:
    target = (config.get("targets") or {}).get(name) or {}
    return set(target.get("provides", []) or []) | set(extra or set())


def missing_capabilities(entry: dict[str, Any], provides: set[str]) -> list[str]:
    return sorted(set(entry.get("requires", []) or []) - provides)


def readiness_gaps(entry: dict[str, Any], roots: dict[str, Path]) -> list[str]:
    """Readiness markers absent from the code. Sources not given with --source are not checked."""
    gaps: list[str] = []
    for item in entry.get("readiness", []) or []:
        root = roots.get(item["source_id"])
        if root is None:
            continue
        path = root / item["path"]
        if not path.is_file():
            gaps.append(f"{item['source_id']}:{item['path']} missing")
            continue
        pattern = item.get("contains")
        if pattern and not re.search(pattern, path.read_text(encoding="utf-8", errors="replace")):
            gaps.append(f"{item['source_id']}:{item['path']} lacks {pattern!r}")
    return gaps


# ---------------------------------------------------------------- fingerprints


def sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_sources(values: list[str]) -> dict[str, Path]:
    roots: dict[str, Path] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"--source must be SOURCE_ID=PATH: {value}")
        key, raw = value.split("=", 1)
        roots[key.strip()] = Path(raw).expanduser().resolve()
    return roots


def fingerprint(tests_dir: Path, config: dict[str, Any], roots: dict[str, Path]) -> list[str]:
    missing: list[str] = []
    for scenario_id, entry in config.get("scenarios", {}).items():
        if entry.get("manual_only"):
            continue
        entry["test_sha256"] = sha256(tests_dir / entry["test"])
        for item in entry.get("evidence", []):
            root = roots.get(item["source_id"])
            if root is None:
                continue  # preserve previous fingerprint for out-of-scope sources
            digest = sha256(root / item["path"])
            if digest is None:
                missing.append(f"{scenario_id}: {item['source_id']}:{item['path']}")
            item["sha256"] = digest
    return missing


def drift(tests_dir: Path, config: dict[str, Any], roots: dict[str, Path]) -> dict[str, Any]:
    stale: dict[str, list[str]] = {}
    skipped: set[str] = set()
    for scenario_id, entry in sorted(config.get("scenarios", {}).items()):
        if entry.get("manual_only"):
            continue
        reasons: list[str] = []
        if entry.get("test_sha256") != sha256(tests_dir / entry["test"]):
            reasons.append(f"test changed: {entry['test']}")
        for item in entry.get("evidence", []):
            root = roots.get(item["source_id"])
            if root is None:
                skipped.add(item["source_id"])
                continue
            current = sha256(root / item["path"])
            if current is None:
                reasons.append(f"evidence missing: {item['source_id']}:{item['path']}")
            elif current != item.get("sha256"):
                reasons.append(f"evidence changed: {item['source_id']}:{item['path']}")
        if reasons:
            stale[scenario_id] = reasons
    return {
        "drift": bool(stale),
        "stale_tests": stale,
        "unchecked_sources": sorted(skipped),
    }


# ---------------------------------------------------------------- acceptance


def parse_acceptance(text: str) -> dict[str, dict[str, str]]:
    """Parse Given/When/Then examples tagged with IDs such as EX-9.1-9."""
    examples: dict[str, dict[str, str]] = {}
    current: str | None = None
    last_key = ""
    for raw in text.splitlines():
        line = raw.strip().lstrip("-*#>|").strip()
        if not line:
            continue
        match = ACCEPTANCE_ID.search(line)
        if match and not re.match(r"^(given|when|then|and|but)\b", line, re.I):
            current = match.group(1)
            title = line[match.end():].strip(" :-—|*`")
            examples[current] = {"title": title, "given": "", "when": "", "then": ""}
            last_key = ""
            continue
        if current is None:
            continue
        keyword = re.match(r"^\**(given|when|then|and|but)\**\s+(.*)$", line, re.I)
        if keyword:
            key = keyword.group(1).lower()
            body = keyword.group(2).strip()
            if key in {"and", "but"}:
                key = last_key or "given"
            existing = examples[current][key]
            examples[current][key] = f"{existing}; {body}" if existing else body
            last_key = key
    return examples


# ---------------------------------------------------------------- run


def resolve_target(
    config: dict[str, Any], name: str | None, base_url: str | None
) -> tuple[str, str, str]:
    if base_url:
        if URL_WITH_USERINFO.match(base_url):
            raise ValueError("--base-url must not embed credentials")
        target = (config.get("targets") or {}).get(name or "", {})
        return (name or "custom", target.get("kind", "custom"), base_url)
    name = name or config.get("default_target") or "local"
    target = (config.get("targets") or {}).get(name)
    if target is None:
        raise ValueError(f"unknown target {name!r}")
    url = target.get("base_url")
    if not url and target.get("base_url_env"):
        url = os.environ.get(target["base_url_env"])
        if not url:
            raise ValueError(f"target {name} needs env var {target['base_url_env']}")
    return (name, target.get("kind", "custom"), url)


def select(
    entry: dict[str, Any], kind: str, wanted: set[str], allow_destructive: bool
) -> str | None:
    """Return None when selected, else the reason it is skipped."""
    tags = set(entry.get("tags", []))
    if wanted and not tags & wanted:
        return "tag not selected"
    if kind == "prod":
        if "destructive" in tags and not allow_destructive:
            return "destructive, skipped on prod"
        if not wanted and not tags & PROD_DEFAULT_TAGS:
            return "not smoke/safe, skipped on prod"
    return None


def all_skipped(output: str) -> bool:
    """True when the runner exited 0 but every collected test was skipped."""
    ran = re.search(r"Ran (\d+) tests?", output)
    skipped = re.search(r"skipped=(\d+)", output)
    if ran and skipped:
        return int(ran.group(1)) == int(skipped.group(1))
    return bool(re.search(r"\b\d+ skipped\b", output)) and not re.search(
        r"\b\d+ passed\b", output
    )


def last_line(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for pattern in (r"^\w*(Error|Exception)\b", r"(Error|assert|expected)", r"(FAIL|failed)"):
        for line in reversed(lines):
            if re.search(pattern, line):
                return line[:140]
    return (lines[-1] if lines else "")[:140]


def run_scenarios(
    tests_dir: Path,
    config: dict[str, Any],
    target_name: str,
    kind: str,
    base_url: str,
    wanted: set[str],
    allow_destructive: bool,
    only: set[str],
    timeout: int,
    provides: set[str] | None = None,
    roots: dict[str, Path] | None = None,
) -> dict[str, dict[str, str]]:
    provides = set(provides or set())
    roots = roots or {}
    results: dict[str, dict[str, str]] = {}
    workdir = (tests_dir / config.get("workdir", ".")).resolve()
    env = {
        **os.environ,
        "PLAYBOOK_BASE_URL": base_url,
        "PLAYBOOK_TARGET": target_name,
        "PLAYBOOK_TARGET_KIND": kind,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PLAYBOOK_PROVIDES": ",".join(sorted(provides)),
    }
    for scenario_id, entry in sorted(config["scenarios"].items()):
        if only and scenario_id not in only:
            continue
        if entry.get("manual_only"):
            results[scenario_id] = {"result": "na", "mode": "Manual", "note": "manual only"}
            continue
        reason = select(entry, kind, wanted, allow_destructive)
        if reason:
            results[scenario_id] = {"result": "na", "mode": "Auto", "note": reason}
            continue
        gaps = readiness_gaps(entry, roots)
        if gaps:
            results[scenario_id] = {"result": "unbuilt", "mode": "Auto", "note": "; ".join(gaps)[:140]}
            continue
        missing = missing_capabilities(entry, provides)
        if missing:
            results[scenario_id] = {
                "result": "env",
                "mode": "Auto",
                "note": f"target lacks {', '.join(missing)}",
            }
            continue
        argv = [sys.executable if part == "{python}" else part for part in entry["run"]]
        try:
            proc = subprocess.run(
                argv, cwd=workdir, env=env, capture_output=True, text=True, timeout=timeout
            )
        except FileNotFoundError:
            results[scenario_id] = {"result": "blocked", "mode": "Auto", "note": f"runner missing: {argv[0]}"}
            continue
        except subprocess.TimeoutExpired:
            results[scenario_id] = {"result": "blocked", "mode": "Auto", "note": f"timeout after {timeout}s"}
            continue
        output = (proc.stdout or "") + "\n" + (proc.stderr or "")
        if proc.returncode == 0:
            skipped = all_skipped(output)
            env_note = ENV_MARKER.search(output) if skipped else None
            unbuilt_note = NOT_BUILT_MARKER.search(output) if skipped else None
            if unbuilt_note and not env_note:
                results[scenario_id] = {
                    "result": "unbuilt",
                    "mode": "Auto",
                    "note": unbuilt_note.group(1).strip()[:140] or "feature not found",
                }
            elif env_note:
                results[scenario_id] = {
                    "result": "env",
                    "mode": "Auto",
                    "note": env_note.group(1).strip()[:140] or "environment",
                }
            else:
                results[scenario_id] = {
                    "result": "blocked" if skipped else "pass",
                    "mode": "Auto",
                    "note": "test skipped" if skipped else "",
                }
        elif proc.returncode == 5:
            results[scenario_id] = {"result": "blocked", "mode": "Auto", "note": "no test collected"}
        else:
            results[scenario_id] = {"result": "fail", "mode": "Auto", "note": last_line(output)}
    return results


def merge_manual(results: dict[str, dict[str, str]], values: list[str]) -> None:
    letters = {v: k for k, v in SYMBOL.items()}
    for value in values:
        if "=" not in value:
            raise ValueError(f"--manual must be ID=P|F|B|E|U|N[:note]: {value}")
        scenario_id, rest = value.split("=", 1)
        letter, _, note = rest.partition(":")
        if letter.upper() not in letters:
            raise ValueError(f"--manual result must be P, F, B, E, U, or N: {value}")
        results[scenario_id.strip()] = {
            "result": letters[letter.upper()],
            "mode": "Manual",
            "note": note.strip(),
        }


def format_stamp(when: datetime) -> str:
    stamp = when.strftime("%Y-%m-%d %H:%M (UTC%z)")
    return re.sub(r"UTC([+-]\d{2})(\d{2})", lambda m: f"UTC{m.group(1)}:{m.group(2)}", stamp)


def render_report(
    config: dict[str, Any],
    results: dict[str, dict[str, str]],
    target_name: str,
    kind: str,
    when: datetime | None = None,
    meta: dict[str, Any] | None = None,
    comparison: dict[str, Any] | None = None,
) -> str:
    when = when or datetime.now().astimezone()
    meta = meta or {}
    counts = {key: 0 for key in SYMBOL}
    for item in results.values():
        counts[item["result"]] += 1
    scenarios = config.get("scenarios", {})
    lines = [f"**Playbook run** · target `{target_name}` ({kind}) · {format_stamp(when)}"]
    ticket = meta.get("ticket")
    if ticket:
        state = f" · state {ticket['state']}" if ticket.get("state") else ""
        title = f" · {ticket['title']}" if ticket.get("title") else ""
        lines.append(f"Ticket {ticket['ref'] or '(none)'}{state}{title}")
    commits = meta.get("commits") or {}
    if commits:
        lines.append(
            "Commits: "
            + ", ".join(
                f"{name} {info['sha'][:10] if info.get('sha') else 'unknown'}"
                + (" +uncommitted" if info.get("dirty") else "")
                for name, info in sorted(commits.items())
            )
        )
    lines += [
        "",
        f"P {counts['pass']} · F {counts['fail']} · B {counts['blocked']}"
        f" · E {counts['env']} · U {counts['unbuilt']} · N {counts['na']}",
        "",
        "| ID | Result | Run | Acceptance | Notes |",
        "| --- | --- | --- | --- | --- |",
    ]
    for scenario_id in sorted(results):
        item = results[scenario_id]
        refs = ", ".join(scenarios.get(scenario_id, {}).get("acceptance", []) or [])
        note = item.get("note", "").replace("|", "/")
        if item.get("scope") == "neighbour":
            note = ("regression check; " + note).strip("; ")
        lines.append(
            f"| {scenario_id} | {SYMBOL[item['result']]} | {item['mode']} | {refs} | {note} |"
        )
    env_blocked = sorted(i for i, item in results.items() if item["result"] == "env")
    if env_blocked:
        lines.append("")
        lines.append(
            f"Environment: {len(env_blocked)} blocked by the target, not by code"
            f" ({', '.join(env_blocked)}). F counts only code or test failures."
        )
    unbuilt = sorted(i for i, item in results.items() if item["result"] == "unbuilt")
    if unbuilt:
        lines.append("")
        lines.append(f"Not built yet: {', '.join(unbuilt)}. Not counted as failures.")
    if comparison:
        lines.append("")
        lines.append(render_comparison(comparison))
    for assumption in meta.get("assumptions", []) or []:
        lines.append("")
        lines.append(f"Assumption: {assumption}")
    acceptance = config.get("acceptance", {}) or {}
    if acceptance:
        covered: dict[str, list[str]] = {}
        for scenario_id, entry in scenarios.items():
            for ref in entry.get("acceptance", []) or []:
                covered.setdefault(ref, []).append(scenario_id)
        uncovered = sorted(set(acceptance) - set(covered))
        failing = sorted(
            ref
            for ref, ids in covered.items()
            if any(results.get(i, {}).get("result") == "fail" for i in ids)
        )
        lines.append("")
        lines.append(
            f"Acceptance: {len(covered)}/{len(acceptance)} examples mapped"
            + (f" · failing {', '.join(failing)}" if failing else "")
            + (f" · unmapped {', '.join(uncovered)}" if uncovered else "")
        )
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- tickets


def ticket_pattern(config: dict[str, Any]) -> re.Pattern[str]:
    pattern = (config.get("tickets") or {}).get("pattern")
    return re.compile(pattern) if pattern else DEFAULT_TICKET


def resolve_ticket(
    config: dict[str, Any], ref: str | None, text: str | None, state: str | None
) -> dict[str, Any] | None:
    """Ticket from an ID, pasted text, or both. Only the reference, title and a hash are kept."""
    if not (ref or text or state):
        return None
    scenarios = config.get("scenarios", {})
    text = text or ""
    if not ref and text:
        for match in ticket_pattern(config).finditer(text):
            value = match.group(0)
            if value not in scenarios and not value.startswith("EX-"):
                ref = value
                break
    title = next((line.strip(" #*-") for line in text.splitlines() if line.strip()), "")
    return {
        "ref": ref or "",
        "title": title[:100],
        "state": state or "",
        "text_sha256": hashlib.sha256(text.encode()).hexdigest() if text else "",
        "mentions": sorted(
            set(SCENARIO_ID_IN_TEXT.findall(text)) & set(scenarios)
            | {m for m in ACCEPTANCE_ID.findall(text) if m in (config.get("acceptance") or {})}
        ),
    }


SCENARIO_ID_IN_TEXT = re.compile(r"\b[A-Z][A-Z0-9]{1,5}-\d{2,3}\b")


def ticket_scenarios(config: dict[str, Any], ticket: dict[str, Any] | None) -> set[str]:
    """Scenarios linked to a ticket: listed under scenario.tickets, or named in its text."""
    if not ticket:
        return set()
    found: set[str] = set()
    mentions = set(ticket.get("mentions", []))
    for scenario_id, entry in config.get("scenarios", {}).items():
        if ticket.get("ref") and ticket["ref"] in (entry.get("tickets") or []):
            found.add(scenario_id)
        if scenario_id in mentions or mentions & set(entry.get("acceptance") or []):
            found.add(scenario_id)
    return found


def apply_ticket_state(
    config: dict[str, Any], results: dict[str, dict[str, str]], ticket: dict[str, Any] | None
) -> None:
    """A failure on a ticket that is not ready for testing yet is Not built yet, not Fail."""
    ready = (config.get("tickets") or {}).get("ready_states")
    if not ticket or not ticket.get("state") or not ready:
        return
    if ticket["state"].casefold() in {s.casefold() for s in ready}:
        return
    for item in results.values():
        if item["result"] == "fail":
            item["result"] = "unbuilt"
            item["note"] = f"ticket is {ticket['state']}; " + item.get("note", "")


# ---------------------------------------------------------------- commits and history


def git(root: Path, *args: str) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, text=True, timeout=30
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    return proc.stdout if proc.returncode == 0 else None


def commit_info(root: Path) -> dict[str, Any]:
    sha = git(root, "rev-parse", "HEAD")
    if sha is None:
        return {"sha": None, "dirty": None}
    status = git(root, "status", "--porcelain") or ""
    return {"sha": sha.strip(), "dirty": bool(status.strip())}


def history_dir(tests_dir: Path, config: dict[str, Any]) -> Path:
    return tests_dir / config.get("history_dir", HISTORY_DIR)


def save_run(tests_dir: Path, config: dict[str, Any], record: dict[str, Any]) -> Path:
    folder = history_dir(tests_dir, config)
    folder.mkdir(parents=True, exist_ok=True)
    base, n = record["run_id"], 1
    while (folder / f"{record['run_id']}.json").exists():
        n += 1
        record["run_id"] = f"{base}-{n}"
    path = folder / f"{record['run_id']}.json"
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def load_runs(tests_dir: Path, config: dict[str, Any]) -> list[dict[str, Any]]:
    runs = []
    folder = history_dir(tests_dir, config)
    for path in sorted(folder.glob("*.json")) if folder.is_dir() else []:
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if isinstance(record, dict) and isinstance(record.get("results"), dict):
            runs.append((record.get("timestamp", ""), path.stat().st_mtime_ns, record))
    return [record for _, _, record in sorted(runs, key=lambda r: (r[0], r[1]))]


def run_id(when: datetime, target: str, ticket: dict[str, Any] | None) -> str:
    slug = re.sub(r"[^A-Za-z0-9-]+", "-", (ticket or {}).get("ref") or "")
    return "-".join(x for x in (when.strftime("%Y%m%dT%H%M%S"), target, slug) if x)


def previous_run(
    runs: list[dict[str, Any]], target: str, scenario_ids: set[str], ticket_ref: str = ""
) -> dict[str, Any] | None:
    """Latest earlier run on the same target that covered any of these scenarios."""
    candidates = [r for r in runs if r.get("target") == target]
    if ticket_ref:
        same = [r for r in candidates if (r.get("ticket") or {}).get("ref") == ticket_ref]
        candidates = same or candidates
    for record in reversed(candidates):
        if not scenario_ids or scenario_ids & set(record["results"]):
            return record
    return None


def compare(previous: dict[str, Any], current: dict[str, dict[str, str]]) -> dict[str, Any]:
    old = previous["results"]
    diff: dict[str, Any] = {
        "since": previous.get("run_id", ""),
        "since_time": previous.get("timestamp", ""),
        "fixed": [], "still_failing": [], "newly_broken": [], "changed": [], "new": [],
    }
    for scenario_id, item in sorted(current.items()):
        now = item["result"]
        if scenario_id not in old:
            diff["new"].append(scenario_id)
            continue
        before = old[scenario_id]["result"]
        if before == "fail" and now == "pass":
            diff["fixed"].append(scenario_id)
        elif before == "fail" and now == "fail":
            diff["still_failing"].append(scenario_id)
        elif before == "pass" and now == "fail":
            diff["newly_broken"].append(scenario_id)
        elif before != now and "na" not in (before, now):
            diff["changed"].append(f"{scenario_id} {SYMBOL[before]}→{SYMBOL[now]}")
    return diff


def render_comparison(diff: dict[str, Any]) -> str:
    def part(label: str, ids: list[str]) -> str:
        return f"{label} {len(ids)}" + (f" ({', '.join(ids)})" if ids else "")

    text = (
        f"Since last run {diff['since']}: "
        + " · ".join(
            [
                part("fixed", diff["fixed"]),
                part("still failing", diff["still_failing"]),
                part("newly broken", diff["newly_broken"]),
            ]
        )
    )
    if diff["changed"]:
        text += " · other changes " + ", ".join(diff["changed"])
    return text


def neighbours(config: dict[str, Any], ids: set[str]) -> set[str]:
    """Scenarios that share a test file, an evidence file, or an acceptance story with ids."""
    scenarios = config.get("scenarios", {})

    def keys(entry: dict[str, Any]) -> set[str]:
        found = {f"test:{entry['test']}"} if entry.get("test") else set()
        found |= {f"ev:{e.get('source_id')}:{e.get('path')}" for e in entry.get("evidence", []) or []}
        found |= {f"story:{ref.rsplit('-', 1)[0]}" for ref in entry.get("acceptance", []) or []}
        return found

    wanted = set().union(*(keys(scenarios[i]) for i in ids if i in scenarios)) if ids else set()
    return {
        scenario_id
        for scenario_id, entry in scenarios.items()
        if scenario_id not in ids and not entry.get("manual_only") and keys(entry) & wanted
    }


# ---------------------------------------------------------------- what changed


def changed_files(root: Path, since: str | None) -> tuple[set[str] | None, str]:
    """Files changed since a commit plus uncommitted ones. None when git cannot tell."""
    if git(root, "rev-parse", "HEAD") is None:
        return None, "not a git checkout"
    files: set[str] = set()
    note = f"since {since[:10]}" if since else "uncommitted only (no earlier commit recorded)"
    if since:
        out = git(root, "diff", "--name-only", f"{since}..HEAD")
        if out is None:
            return None, f"commit {since[:10]} not found"
        files |= {line for line in out.splitlines() if line}
    status = git(root, "status", "--porcelain") or ""
    files |= {line[3:].split(" -> ")[-1] for line in status.splitlines() if len(line) > 3}
    return files, note


def what_changed(
    tests_dir: Path, config: dict[str, Any], roots: dict[str, Path], since: dict[str, str]
) -> dict[str, Any]:
    runs = load_runs(tests_dir, config)
    last = runs[-1] if runs else None
    affected: dict[str, list[str]] = {}
    report: dict[str, Any] = {"sources": {}, "affected": affected, "unmapped": {}}
    scenarios = config.get("scenarios", {})
    for source_id, root in sorted(roots.items()):
        base = since.get(source_id) or ((last or {}).get("commits", {}).get(source_id) or {}).get("sha")
        files, note = changed_files(root, base)
        if files is None:
            # No git history: fall back to fingerprints recorded in the config.
            stale = drift(tests_dir, config, {source_id: root})["stale_tests"]
            for scenario_id, reasons in stale.items():
                affected.setdefault(scenario_id, []).extend(r for r in reasons if source_id in r)
            report["sources"][source_id] = {"method": "fingerprints", "note": note}
            continue
        report["sources"][source_id] = {"method": "git", "note": note, "files": len(files)}
        mapped: set[str] = set()
        for scenario_id, entry in scenarios.items():
            paths = [i["path"] for i in (entry.get("evidence") or []) + (entry.get("readiness") or [])
                     if i.get("source_id") == source_id]
            for path in paths:
                hits = [f for f in files if f == path or f.startswith(path.rstrip("/") + "/")]
                if hits:
                    mapped.update(hits)
                    affected.setdefault(scenario_id, []).append(f"{source_id}:{path} changed")
        unmapped = sorted(files - mapped)
        if unmapped:
            report["unmapped"][source_id] = unmapped
    for scenario_id, entry in scenarios.items():
        if entry.get("manual_only"):
            continue
        if entry.get("test_sha256") and entry.get("test_sha256") != sha256(tests_dir / entry["test"]):
            affected.setdefault(scenario_id, []).append(f"test changed: {entry['test']}")
    for scenario_id in affected:
        affected[scenario_id] = sorted(set(affected[scenario_id]))
    report["last_run"] = (last or {}).get("run_id", "")
    report["suggest"] = sorted(affected)
    return report


def render_changed(report: dict[str, Any], tests_arg: str) -> str:
    lines = [f"**What changed** · last run {report['last_run'] or '(none recorded)'}", ""]
    for source_id, info in report["sources"].items():
        lines.append(f"- {source_id}: {info['method']}, {info['note']}" + (
            f", {info['files']} files" if "files" in info else ""))
    lines.append("")
    if report["affected"]:
        lines.append("| Scenario | Why |")
        lines.append("| --- | --- |")
        for scenario_id, reasons in sorted(report["affected"].items()):
            lines.append(f"| {scenario_id} | {'; '.join(reasons)} |")
        lines.append("")
        lines.append(
            f"Suggested (not run): playbook_tests.py retest {tests_arg} --only "
            + ",".join(report["suggest"])
        )
    else:
        lines.append("No scenario is affected by the recorded changes.")
    for source_id, files in report["unmapped"].items():
        lines.append("")
        lines.append(
            f"Unmapped {source_id} changes ({len(files)}): {', '.join(files[:15])}"
            + (" ..." if len(files) > 15 else "")
            + ". No scenario cites them; judge whether a smoke run is worth it."
        )
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- cli


def playbook_ids(playbook: Path) -> set[str]:
    heading = re.compile(r"^## ([A-Z][A-Z0-9]{1,5}-\d{2,3}):", re.M)
    ids: set[str] = set()
    for path in playbook.glob("[0-9][0-9]-*.md"):
        ids.update(heading.findall(path.read_text(encoding="utf-8")))
    return ids


def add_run_arguments(run: argparse.ArgumentParser) -> None:
    run.add_argument("tests_dir")
    run.add_argument("--target", help="Target name from the config")
    run.add_argument("--base-url", help="Custom URL for this run (no credentials)")
    run.add_argument("--tags", default="", help="Comma list: smoke,safe,destructive")
    run.add_argument("--only", default="", help="Comma list of scenario IDs")
    run.add_argument("--allow-destructive", action="store_true", help="Allow destructive on prod")
    run.add_argument("--manual", action="append", default=[], metavar="ID=P|F|B|E|U|N[:note]")
    run.add_argument(
        "--provide",
        default="",
        help="Comma list of extra capabilities available for this run (e.g. s3,sqs)",
    )
    run.add_argument(
        "--source", action="append", default=[], metavar="SOURCE_ID=PATH",
        help="Code checkout: records its commit and enables readiness checks",
    )
    run.add_argument("--ticket", help="Ticket reference, e.g. ABC-123 (optional)")
    run.add_argument("--ticket-file", help="File with the ticket text (pasted or exported)")
    run.add_argument("--ticket-text", help="Ticket text inline")
    run.add_argument("--ticket-state", help="Ticket state as seen on the tracker, if known")
    run.add_argument("--no-history", action="store_true", help="Do not record this run")
    run.add_argument("--timeout", type=int, default=300)
    run.add_argument("--output", help="Also write the Markdown summary here")
    run.add_argument("--json", action="store_true", help="Print JSON instead of Markdown")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="Validate playbook-tests.json")
    check.add_argument("tests_dir")
    check.add_argument("--playbook", help="Cross-check scenario IDs against this playbook")

    fp = sub.add_parser("fingerprint", help="Record test and evidence hashes")
    fp.add_argument("tests_dir")
    fp.add_argument("--source", action="append", default=[], metavar="SOURCE_ID=PATH")

    dr = sub.add_parser("drift", help="Exit 1 when a test or its evidence changed")
    dr.add_argument("tests_dir")
    dr.add_argument("--source", action="append", default=[], metavar="SOURCE_ID=PATH")

    ac = sub.add_parser("import-acceptance", help="Import Given/When/Then examples")
    ac.add_argument("tests_dir")
    ac.add_argument("file", help="Markdown or text with IDs such as EX-9.1-9")

    add_run_arguments(sub.add_parser("run", help="Run selected tests and print a pasteable summary"))
    retest = sub.add_parser(
        "retest", help="Rerun what failed last time (or a ticket's scenarios) plus neighbours; diff"
    )
    add_run_arguments(retest)
    retest.add_argument("--no-neighbours", action="store_true", help="Skip the regression check")

    hist = sub.add_parser("history", help="List recorded runs")
    hist.add_argument("tests_dir")
    hist.add_argument("--ticket", help="Only runs for this ticket")
    hist.add_argument("--scenario", help="Show one scenario's results over time")
    hist.add_argument("--limit", type=int, default=20)

    ch = sub.add_parser("changed", help="Map code changes since the last run to scenarios (runs nothing)")
    ch.add_argument("tests_dir")
    ch.add_argument("--source", action="append", default=[], metavar="SOURCE_ID=PATH")
    ch.add_argument("--since", action="append", default=[], metavar="SOURCE_ID=REV",
                    help="Compare from this commit instead of the last run's")
    ch.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def csv(value: str) -> set[str]:
    return {t.strip() for t in (value or "").split(",") if t.strip()}


def execute_run(args: argparse.Namespace, tests_dir: Path, config: dict[str, Any]) -> tuple[str, int, dict[str, Any]]:
    errors = check_config(config, tests_dir)
    if errors:
        raise ValueError("invalid config: " + "; ".join(errors))
    name, kind, url = resolve_target(config, args.target, args.base_url)
    wanted = csv(args.tags)
    if wanted - TAGS:
        raise ValueError(f"unknown tags: {sorted(wanted - TAGS)}")
    only = csv(args.only)
    unknown = only - set(config["scenarios"])
    if unknown:
        raise ValueError(f"unknown scenario IDs: {sorted(unknown)}")
    extra = csv(args.provide)
    for cap in extra:
        bad = capability_errors(config, "--provide", cap)
        if bad:
            raise ValueError(bad[0])
    provides = target_provides(config, name, extra)
    roots = parse_sources(args.source)
    text = Path(args.ticket_file).expanduser().read_text(encoding="utf-8") if args.ticket_file else args.ticket_text
    ticket = resolve_ticket(config, args.ticket, text, args.ticket_state)
    assumptions: list[str] = []
    runs = load_runs(tests_dir, config)
    linked = ticket_scenarios(config, ticket)

    focus = set(only)
    if not focus and linked:
        focus = linked
    if args.command == "retest" and not focus:
        last = previous_run(runs, name, set())
        if last is None:
            raise ValueError("nothing to retest: no earlier run on this target; use run first")
        focus = {i for i, item in last["results"].items() if item["result"] in NOT_OK}
        focus &= set(config["scenarios"])
        if not focus:
            assumptions.append(f"last run {last['run_id']} had nothing failing; reran all its scenarios")
            focus = set(last["results"]) & set(config["scenarios"])
    if ticket and not linked and not only:
        assumptions.append(
            f"no scenario is linked to ticket {ticket['ref'] or '(text)'}; ran the normal selection."
            " Link scenarios with scenario.tickets or name scenario/acceptance IDs in the ticket."
        )
    extra_ids: set[str] = set()
    if args.command == "retest" and not getattr(args, "no_neighbours", False):
        extra_ids = neighbours(config, focus)
    selection = (focus | extra_ids) if focus else set()
    results = run_scenarios(
        tests_dir, config, name, kind, url, wanted, args.allow_destructive, selection,
        args.timeout, provides, roots,
    )
    for scenario_id in extra_ids & set(results):
        results[scenario_id]["scope"] = "neighbour"
    merge_manual(results, args.manual)
    apply_ticket_state(config, results, ticket)

    when = datetime.now().astimezone()
    commits = {source_id: commit_info(root) for source_id, root in roots.items()}
    commits.setdefault("tests", commit_info(tests_dir))
    previous = previous_run(runs, name, set(results), (ticket or {}).get("ref", ""))
    comparison = compare(previous, results) if previous else None
    meta = {"ticket": ticket, "commits": commits, "assumptions": assumptions}
    record = {
        "schema_version": 1,
        "run_id": run_id(when, name, ticket),
        "timestamp": when.isoformat(timespec="seconds"),
        "command": args.command,
        "target": name,
        "kind": kind,
        "base_url": url,
        "provides": sorted(provides),
        "selection": {"tags": sorted(wanted), "only": sorted(selection)},
        **meta,
        "comparison": comparison,
        "results": results,
    }
    if not args.no_history:
        save_run(tests_dir, config, record)
    report = render_report(config, results, name, kind, when, meta, comparison)
    if args.output:
        Path(args.output).expanduser().write_text(report, encoding="utf-8")
    code = 1 if any(item["result"] == "fail" for item in results.values()) else 0
    return report, code, record


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    tests_dir = Path(args.tests_dir).expanduser().resolve()
    try:
        config = load_config(tests_dir)
        if args.command == "check":
            ids = playbook_ids(Path(args.playbook).expanduser()) if args.playbook else None
            errors = check_config(config, tests_dir, ids)
            print(json.dumps({"valid": not errors, "errors": errors}, indent=2))
            return 1 if errors else 0
        if args.command == "fingerprint":
            missing = fingerprint(tests_dir, config, parse_sources(args.source))
            if missing:
                raise ValueError("evidence not found: " + "; ".join(missing))
            save_config(tests_dir, config)
            print(json.dumps({"fingerprinted": True}, indent=2))
            return 0
        if args.command == "drift":
            report = drift(tests_dir, config, parse_sources(args.source))
            print(json.dumps(report, indent=2, sort_keys=True))
            return 1 if report["drift"] else 0
        if args.command == "import-acceptance":
            text = Path(args.file).expanduser().read_text(encoding="utf-8")
            examples = parse_acceptance(text)
            if not examples:
                raise ValueError("no acceptance examples with IDs found")
            config.setdefault("acceptance", {}).update(examples)
            save_config(tests_dir, config)
            print(json.dumps({"imported": sorted(examples)}, indent=2))
            return 0
        if args.command == "history":
            runs = load_runs(tests_dir, config)
            if args.ticket:
                runs = [r for r in runs if (r.get("ticket") or {}).get("ref") == args.ticket]
            rows = []
            for record in runs[-args.limit:]:
                counts: dict[str, int] = {}
                for item in record["results"].values():
                    counts[SYMBOL[item["result"]]] = counts.get(SYMBOL[item["result"]], 0) + 1
                row = {
                    "run_id": record.get("run_id"),
                    "timestamp": record.get("timestamp"),
                    "target": record.get("target"),
                    "ticket": (record.get("ticket") or {}).get("ref", ""),
                    "commits": {k: (v.get("sha") or "")[:10] for k, v in (record.get("commits") or {}).items()},
                    "counts": counts,
                }
                if args.scenario:
                    item = record["results"].get(args.scenario)
                    if not item:
                        continue
                    row["result"] = SYMBOL[item["result"]]
                    row["note"] = item.get("note", "")
                rows.append(row)
            print(json.dumps({"runs": rows}, indent=2, sort_keys=True))
            return 0
        if args.command == "changed":
            since = {}
            for value in args.since:
                if "=" not in value:
                    raise ValueError(f"--since must be SOURCE_ID=REV: {value}")
                key, rev = value.split("=", 1)
                since[key.strip()] = rev.strip()
            report = what_changed(tests_dir, config, parse_sources(args.source), since)
            if args.json:
                print(json.dumps(report, indent=2, sort_keys=True))
            else:
                print(render_changed(report, args.tests_dir), end="")
            return 0
        report, code, record = execute_run(args, tests_dir, config)
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(record, indent=2, sort_keys=True))
    else:
        print(report, end="")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
