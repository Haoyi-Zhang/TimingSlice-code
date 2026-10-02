from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from src import cases, checker, producer
from tests.support import record

ROOT = Path(__file__).resolve().parents[1]


class ExpressionAndModelTests(unittest.TestCase):
    def test_small_cross_interpreter_operator_set(self) -> None:
        vectors = [
            (["and", ["const", 2, 3], ["const", 2, 1]], 1),
            (["or", ["const", 2, 2], ["const", 2, 1]], 3),
            (["xor", ["const", 2, 3], ["const", 2, 1]], 2),
            (["add", ["const", 2, 3], ["const", 2, 1]], 0),
            (["sub", ["const", 2, 0], ["const", 2, 1]], 3),
            (["eq", ["const", 2, 2], ["const", 2, 2]], 1),
            (["ult", ["const", 2, 1], ["const", 2, 2]], 1),
            (["not", ["const", 2, 1]], 2),
            (["concat", ["const", 2, 2], ["const", 2, 1]], 9),
            (["slice", ["const", 4, 13], 1, 2], 2),
        ]
        for expression, expected in vectors:
            with self.subTest(expression=expression):
                pnode = producer.parse(expression, {})
                width, program = checker.compile_expression(expression, {})
                self.assertEqual(pnode.width, width)
                self.assertEqual(producer.evaluate(pnode, {}), expected)
                self.assertEqual(checker.execute(program, {}), expected)
        record("operator_value_checks", len(vectors))

    def test_malformed_expressions_are_rejected_by_both_parsers(self) -> None:
        malformed = [
            [],
            ["const", 0, 0],
            ["var", "missing"],
            ["mux", ["const", 2, 0], ["const", 1, 0], ["const", 1, 1]],
            ["concat", ["const", 16, 0], ["const", 1, 0]],
            ["foreign", ["const", 1, 0]],
        ]
        for expression in malformed:
            with self.subTest(expression=expression):
                with self.assertRaises((producer.ModelError, ValueError, IndexError)):
                    producer.parse(expression, {})
                with self.assertRaises((checker.Rejected, ValueError, IndexError)):
                    checker.compile_expression(expression, {})

    def test_models_snapshot_caller_data(self) -> None:
        raw = copy.deepcopy(cases.controls()[2])
        pmodel = producer.Model(raw)
        cmodel = checker.Semantics(raw)
        raw["registers"][0]["init"] = 3
        self.assertEqual(pmodel.raw["registers"][0]["init"], 0)
        self.assertEqual(cmodel.data["registers"][0]["init"], 0)

    def test_duplicate_json_keys_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "duplicate.json"
            path.write_text('{"x": 0, "x": 1}\n')
            with self.assertRaises(checker.Rejected):
                checker.load(path)

    def test_fixture_generator_matches_all_stored_models(self) -> None:
        generated = cases.controls() + [raw for raw, _ in cases.reductions()]
        fixtures = {path.stem: json.loads(path.read_text()) for path in (ROOT / "cases").glob("*.json")}
        self.assertEqual(len(generated), 109)
        self.assertEqual(set(fixtures), {raw["id"] for raw in generated})
        for raw in generated:
            self.assertEqual(fixtures[raw["id"]], raw)


class CertificateRegressionTests(unittest.TestCase):
    def _verify(self, name: str) -> dict:
        source = json.loads((ROOT / "cases" / f"{name}.json").read_text())
        bundle = json.loads((ROOT / "results" / "clean-reproduction" / "bundles" /
                             f"{name}-first-hit.json").read_text())
        result = checker.verify_bundle(source, bundle)
        record("checker_semantic_obligations", result["work"]["observations"] + result["work"]["successors"])
        return result

    def test_three_small_retained_bundles_accept(self) -> None:
        for name in ("initial-completion", "joint-omission", "zero-cancellation"):
            with self.subTest(name=name):
                result = self._verify(name)
                self.assertTrue(result["accepted"], result)
                self.assertEqual(result["claim"], "inclusion-minimal")

    def test_missing_initial_pair_is_rejected(self) -> None:
        source = json.loads((ROOT / "cases" / "initial-completion.json").read_text())
        bundle = json.loads((ROOT / "results" / "clean-reproduction" / "bundles" /
                             "initial-completion-first-hit.json").read_text())
        bundle["preservation"]["frontiers"][0] = []
        result = checker.verify_bundle(source, bundle)
        record("checker_semantic_obligations", result["work"]["observations"] + result["work"]["successors"])
        self.assertFalse(result["accepted"])
        self.assertEqual(result["status"], "rejected")
        self.assertIn("initial pair", result["reason"])

    def test_tampered_output_program_is_rejected(self) -> None:
        source = json.loads((ROOT / "cases" / "initial-completion.json").read_text())
        bundle = json.loads((ROOT / "results" / "clean-reproduction" / "bundles" /
                             "initial-completion-first-hit.json").read_text())
        bundle["timing_model"]["done"] = ["const", 1, 0]
        result = checker.verify_bundle(source, bundle)
        record("checker_semantic_obligations", result["work"]["observations"] + result["work"]["successors"])
        self.assertFalse(result["accepted"])
        self.assertEqual(result["status"], "rejected")
        self.assertIn("emitted timing program", result["reason"])

    def test_zero_budget_is_unknown_not_rejected(self) -> None:
        source = json.loads((ROOT / "cases" / "initial-completion.json").read_text())
        bundle = json.loads((ROOT / "results" / "clean-reproduction" / "bundles" /
                             "initial-completion-first-hit.json").read_text())
        result = checker.verify_bundle(source, bundle, limit=0)
        self.assertFalse(result["accepted"])
        self.assertEqual(result["status"], "unknown")


if __name__ == "__main__":
    unittest.main()
