"""Opt-in host isolation tests: LAC_TEST_SANDBOX=1 python -m unittest ..."""

import os
import socket
from pathlib import Path
import sys
import tempfile
import unittest

from lac.process import run


@unittest.skipUnless(os.environ.get("LAC_TEST_SANDBOX") == "1", "set LAC_TEST_SANDBOX=1 to test host isolation")
class SandboxTests(unittest.TestCase):
    def test_outside_file_and_network_are_denied(self):
        with tempfile.TemporaryDirectory(prefix="lac-isolation-") as tmp, socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            root = Path(tmp)
            outside = root / "evaluator-only.txt"
            outside.write_text("test sentinel, not a credential")
            script = """
import socket, sys
try:
    open(sys.argv[1]).read()
except PermissionError:
    pass
except FileNotFoundError:
    pass  # Linux namespace hides the containing directory entirely.
else:
    raise RuntimeError('outside file is readable')
try:
    socket.create_connection(('127.0.0.1', int(sys.argv[2])), timeout=0.2)
except OSError:
    pass
else:
    raise RuntimeError('unexpected network access')
print('isolated')
"""
            result = run([sys.executable, "-I", "-S", "-c", script, str(outside), str(listener.getsockname()[1])],
                         root / "job", 5, execution="sandbox")
            self.assertEqual(result["stdout"].strip(), "isolated")
