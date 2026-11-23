"""Loopback-only, one-click pause control for the independent Windows monitor."""
from __future__ import annotations

import argparse
import hmac
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


def make_handler(state_dir: Path, port: int):
    class Handler(BaseHTTPRequestHandler):
        # Bound the time a stalled browser can occupy this small local server.
        timeout = 5

        def log_message(self, *args):
            pass  # Never log URLs containing the pause token.

        def respond(self, status: int, text: str):
            body = text.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.headers.get("Host") != f"127.0.0.1:{port}":
                self.respond(403, "Invalid host.")
                return
            if self.path == "/health":
                self.respond(200, "company-monitor-control")
                return
            try:
                config = json.loads((state_dir / "config.json").read_text(encoding="utf-8-sig"))
                expected = "/stop/" + config["StopToken"]
                if not hmac.compare_digest(self.path.encode(), expected.encode()):
                    self.respond(404, "Unknown control link.")
                    return
                # GET intentionally pauses: the user requested a single email click.
                # The random token is the capability; this listener is never public.
                (state_dir / "paused").touch()
                self.respond(200, "CompanyBot alert emails are STOPPED.\nTo resume, run Manage-CompanyMonitor.ps1 -Action Start on this PC.")
            except (OSError, ValueError, KeyError):
                self.respond(500, "Could not pause alerts. Run Manage-CompanyMonitor.ps1 -Action Stop on this PC.")

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--port", type=int, default=18761)
    args = parser.parse_args()
    with HTTPServer(("127.0.0.1", args.port), make_handler(args.state_dir, args.port)) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
