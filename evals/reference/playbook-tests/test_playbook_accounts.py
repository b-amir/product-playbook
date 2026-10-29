"""Runnable checks for the Accounts chapter. IDs match the playbook scenarios.

Target comes from PLAYBOOK_BASE_URL (set by scripts/playbook_tests.py run).
Evidence: openapi.yaml (POST /accounts -> 201 id,name), app.py (empty name -> 400),
tests/test_accounts.py (same request shape).
"""

from __future__ import annotations

import json
import os
import unittest
from urllib import error, request

BASE_URL = os.environ.get("PLAYBOOK_BASE_URL", "http://127.0.0.1:8765").rstrip("/")


def post_accounts(body: dict) -> tuple[int, dict]:
    req = request.Request(
        f"{BASE_URL}/accounts",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=5) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw) if raw else {}
    except error.HTTPError as http_error:
        return http_error.code, {}


class Accounts(unittest.TestCase):
    def test_ACC_01_create_account(self) -> None:
        status, body = post_accounts({"name": "Playbook Tester"})
        self.assertEqual(status, 201)
        self.assertTrue(body.get("id"))
        self.assertEqual(body.get("name"), "Playbook Tester")

    def test_ACC_02_reject_empty_name(self) -> None:
        status, _ = post_accounts({"name": ""})
        self.assertEqual(status, 400)


if __name__ == "__main__":
    unittest.main()
