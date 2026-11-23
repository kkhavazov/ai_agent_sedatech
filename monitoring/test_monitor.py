import json
import ssl
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import HTTPServer
from pathlib import Path
from unittest.mock import patch

from send_alert import send_alert
from stop_control import make_handler


class StopControlTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.token = "abc123" * 10
        (self.root / "config.json").write_text(json.dumps({"StopToken": self.token}))
        self.server = HTTPServer(("127.0.0.1", 0), make_handler(self.root, 0))
        port = self.server.server_address[1]
        self.server.RequestHandlerClass = make_handler(self.root, port)
        self.url = f"http://127.0.0.1:{port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()
        self.temp.cleanup()

    def test_valid_email_link_pauses_immediately_and_is_idempotent(self):
        for _ in range(2):
            with urllib.request.urlopen(self.url + "/stop/" + self.token, timeout=2) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertTrue((self.root / "paused").exists())

    def test_health_does_not_pause(self):
        with urllib.request.urlopen(self.url + "/health", timeout=2) as response:
            self.assertEqual(response.read(), b"company-monitor-control")
        self.assertFalse((self.root / "paused").exists())

    def test_wrong_token_and_host_cannot_pause(self):
        for request, expected in [
            (self.url + "/stop/wrong", 404),
            (urllib.request.Request(self.url + "/stop/" + self.token, headers={"Host": "evil.example"}), 403),
        ]:
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(request, timeout=2)
            self.assertEqual(error.exception.code, expected)
        self.assertFalse((self.root / "paused").exists())


class SmtpTests(unittest.TestCase):
    @patch("send_alert.smtplib.SMTP_SSL")
    def test_ssl_self_addressed_message_and_stop_button(self, smtp):
        data = {
            "Address": "monitor@example.test", "Username": "monitor@example.test",
            "Host": "smtp.example.test", "Port": 465, "Password": "private-password",
            "Subject": "Monitor alert", "Body": "MCP <failed>",
            "StopUrl": "http://127.0.0.1:18761/stop/test-token",
        }
        send_alert(data)
        self.assertEqual(smtp.call_args.args, ("smtp.example.test", 465))
        self.assertEqual(smtp.call_args.kwargs["context"].verify_mode, ssl.CERT_REQUIRED)
        session = smtp.return_value.__enter__.return_value
        session.login.assert_called_once_with(data["Username"], data["Password"])
        message = session.send_message.call_args.args[0]
        self.assertEqual(message["From"], message["To"])
        html = message.get_body(preferencelist=("html",)).get_content()
        self.assertIn('href="' + data["StopUrl"] + '"', html)
        self.assertIn("MCP &lt;failed&gt;", html)
        self.assertNotIn(data["Password"], message.as_string())


if __name__ == "__main__":
    unittest.main()
