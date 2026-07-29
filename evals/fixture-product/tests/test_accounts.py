from __future__ import annotations

import json
import unittest
from urllib import error, request


class AccountTests(unittest.TestCase):
    def test_create_account_returns_201(self) -> None:
        payload = json.dumps({"name": "Fixture User"}).encode("utf-8")
        req = request.Request(
            "http://127.0.0.1:8765/accounts",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=1) as response:
                body = json.loads(response.read().decode("utf-8"))
                self.assertEqual(response.status, 201)
                self.assertIn("id", body)
                self.assertEqual(body["name"], "Fixture User")
        except error.URLError:
            self.skipTest("fixture server not running")


if __name__ == "__main__":
    unittest.main()
