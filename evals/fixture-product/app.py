"""Minimal in-memory accounts API for evals."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import uuid


ACCOUNTS: dict[str, dict[str, str]] = {}


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/accounts":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length) or b"{}")
        name = str(body.get("name", "")).strip()
        if not name:
            self.send_response(400)
            self.end_headers()
            return
        account_id = str(uuid.uuid4())
        ACCOUNTS[account_id] = {"id": account_id, "name": name}
        payload = json.dumps(ACCOUNTS[account_id]).encode("utf-8")
        self.send_response(201)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        return


def main() -> None:
    server = HTTPServer(("127.0.0.1", 8765), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
