from pathlib import Path
import shutil
import sys
import tempfile
import unittest

from lac.data import Suite
from lac.demo_compiler import compile_source
from lac.process import ProcessError, run
from lac.study import compiler_assembly
from lac.toolchain import Evaluator, Toolchain

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("clang"), "native tests require clang")
class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="lac-tests-")
        cls.root = Path(cls.tmp.name)
        cls.config = {"execution": "local", "timeout_seconds": 2, "repeats": 2,
                      "random_cases": 2, "sizes": [8], "iterations": 1000, "min_batch_ns": 1000000}
        cls.tc = Toolchain(cls.config, cls.root / "tc")
        cls.target = cls.tc.metadata()["target"]
        cls.task = Suite(ROOT / "benchmarks/smoke/suite.json").select("dev")[0]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_native_candidate_and_wrong_answer(self):
        evaluator = Evaluator(self.tc)
        assembly = compile_source(self.task["code"], self.target)
        result = evaluator.evaluate(self.task, assembly, self.root / "valid", "search", 0)
        self.assertEqual(result["status"], "pass", result)
        wrong = compile_source("uint64_t kernel() { return 7; }", self.target)
        result = evaluator.evaluate(self.task, wrong, self.root / "wrong", "search", 0)
        self.assertEqual(result["status"], "wrong_answer")
        result = evaluator.evaluate(self.task, "not an instruction", self.root / "bad", "search", 0)
        self.assertEqual(result["status"], "build_error")

    def test_reusable_compiler_and_delegation_policy(self):
        code = (ROOT / "lac/demo_compiler.py").read_text()
        assembly, _ = compiler_assembly(code, self.task, self.target, self.root / "compiler", self.config)
        self.assertIn("kernel", assembly)
        with self.assertRaises(ProcessError) as caught:
            compiler_assembly("import os\nos.system('clang --version')", self.task,
                              self.target, self.root / "delegate", self.config)
        self.assertIn("forbids os.system", str(caught.exception))

    def test_deadline_and_timeout(self):
        with self.assertRaises(ProcessError) as caught:
            run([sys.executable, "-c", "while True: pass"], self.root / "hang", 0.1)
        self.assertEqual(caught.exception.kind, "timeout")

    def test_child_does_not_inherit_api_credentials(self):
        import os
        from unittest.mock import patch
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-only-secret"}):
            result = run([sys.executable, "-c", "import os; print(os.environ.get('OPENAI_API_KEY', 'absent'))"], self.root / "env")
        self.assertEqual(result["stdout"].strip(), "absent")


if __name__ == "__main__":
    unittest.main()
