import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import tempfile
import threading
import unittest

from lac.providers import Provider


class Handler(BaseHTTPRequestHandler):
    payload = None

    def log_message(self, *args):
        pass

    def do_POST(self):
        Handler.payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"model": "local-test", "choices": [{"message": {"content": '{"artifact":"ret"}'},
                           "finish_reason": "stop"}], "usage": {"prompt_tokens": 20, "completion_tokens": 10}}).encode())


class ProviderTests(unittest.TestCase):
    def test_chat_protocol_and_usage_without_paid_api(self):
        try:
            server = HTTPServer(("127.0.0.1", 0), Handler)
        except PermissionError:
            self.skipTest("environment disallows loopback sockets")
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            provider = Provider({"kind": "chat", "base_url": f"http://127.0.0.1:{server.server_port}/v1", "model": "local-test"})
            with tempfile.TemporaryDirectory() as tmp:
                result = provider.generate([{"role": "user", "content": "test"}], {}, 2, Path(tmp))
            self.assertEqual(result["usage"], {"input_tokens": 20, "output_tokens": 10})
            self.assertEqual(Handler.payload["max_completion_tokens"], 8192)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
