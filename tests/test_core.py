import copy
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from lac.data import Suite, cases, digest, write_json
from lac.providers import Budget, BudgetExhausted, parse_artifact
from lac.stats import geomean, paired_summary
from lac.study import final_evaluate, model_messages, summarize
from lac.toolchain import validate_assembly

ROOT = Path(__file__).resolve().parents[1]


class CoreTests(unittest.TestCase):
    def test_phase_streams_are_reproducible_and_distinct(self):
        self.assertEqual(cases("p", "search", 1), cases("p", "search", 1))
        self.assertNotEqual(cases("p", "search", 1)[22:], cases("p", "selection", 1)[22:])
        self.assertNotEqual(cases("p", "selection", 1)[22:], cases("p", "final", 2)[22:])

    def test_suite_hash_tampering_and_family_leakage(self):
        suite = Suite(ROOT / "benchmarks/smoke/suite.json")
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            data = copy.deepcopy(suite.data)
            for task in data["tasks"]:
                (p / task["source"]).write_text(task["code"])
            write_json(p / "suite.json", data)
            Suite(p / "suite.json")
            (p / data["tasks"][0]["source"]).write_text("tampered")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                Suite(p / "suite.json")
            (p / data["tasks"][0]["source"]).write_text(data["tasks"][0]["code"])
            data["tasks"][-1]["family"] = data["tasks"][0]["family"]
            write_json(p / "suite.json", data)
            with self.assertRaisesRegex(ValueError, "leaks"):
                Suite(p / "suite.json")

    def test_budget_charges_invalid_responses_and_stops_on_unknown_usage(self):
        b = Budget({"max_calls": 1, "max_tokens": 10, "max_seconds": 20})
        b.reserve()
        b.charge({"input_tokens": 7, "output_tokens": 8})
        with self.assertRaises(BudgetExhausted):
            b.reserve()
        self.assertEqual(b.snapshot()["output_tokens"], 8)
        b = Budget({})
        b.charge(None)
        with self.assertRaises(BudgetExhausted):
            b.reserve()
        b = Budget({"max_seconds": 1})
        b.started = time.monotonic() - 2
        with self.assertRaises(BudgetExhausted):
            b.reserve()

    def test_artifact_validation(self):
        self.assertEqual(parse_artifact('```json\n{"artifact":"ret"}\n```')["artifact"], "ret")
        for bad in ('{}', '{"artifact": 42}', 'not JSON'):
            with self.assertRaises(ValueError):
                parse_artifact(bad)
        for asm in ('.include "/secret"', 'foo:; .incbin "hidden"'):
            with self.assertRaises(ValueError):
                validate_assembly(asm)

    def test_failures_remain_in_denominators(self):
        summary = summarize({"results": [
            {"status": "pass", "speedup": 2, "faster": True},
            {"status": "wrong_answer"}, {"status": "build_error"}]})
        self.assertEqual(summary["correctness_rate"], 1 / 3)
        self.assertEqual(summary["correct_and_faster_rate"], 1 / 3)
        self.assertEqual(summary["geomean_speedup_correct_subset"], 2)

    def test_paired_statistics(self):
        pairs = [{"baseline_ns": 200, "candidate_ns": 100}] * 7
        self.assertTrue(paired_summary(pairs)["faster"])
        self.assertFalse(paired_summary(pairs[:2])["faster"])
        self.assertEqual(geomean([0.5, 2]), 1)

    def test_timing_failure_does_not_erase_passed_input_checks(self):
        summary = summarize({"results": [{"status": "unstable_timing", "compiled": True, "correctness_passed": True}]})
        self.assertEqual(summary["compile_rate"], 1)
        self.assertEqual(summary["correctness_rate"], 1)
        self.assertEqual(summary["passed"], 0)
        self.assertIsNone(summary["geomean_speedup_correct_subset"])

    def test_prompt_has_only_supplied_programs_and_search_feedback(self):
        suite = Suite(ROOT / "benchmarks/smoke/suite.json")
        messages = json.dumps(model_messages("compiler", suite.select("dev"), "aarch64-linux-gnu", None, []))
        self.assertIn("affine", messages)
        self.assertNotIn("xor_mix", messages)
        self.assertNotIn("final_seed", messages)

    def test_freeze_manifest_modification_rejected_before_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            write_json(p / "run.json", {"state": "frozen"})
            write_json(p / "freeze.json", {"manifest_sha256": digest(b"not the manifest")})
            with self.assertRaisesRegex(ValueError, "modified"):
                final_evaluate(None, p, "dev", 1)


if __name__ == "__main__":
    unittest.main()
