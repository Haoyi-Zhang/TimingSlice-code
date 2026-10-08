"""Owned width-boundary cases with explicit expected Boolean semantics."""
from __future__ import annotations

import unittest

from src import checker, producer, rtl_frontend, rtl_translation_checker
from tests.test_source_semantics import manifest


def source_for(condition: str) -> str:
    return ("module owned(input clk, input [1:0] u, output reg q);\n"
            f"always @(posedge clk) if ({condition}) q <= 1'b1; else q <= 1'b0;\n"
            "endmodule\n")


class LiteralWidthTests(unittest.TestCase):
    def translate(self, source: str) -> dict:
        raw, _ = rtl_frontend.translate(
            source, module_name="owned", model_id="owned-source-regression", clock="clk",
            done_expression="q", horizon=1, domains={"u": [0, 1, 2, 3]},
            initial_state={"q": 0}, cuttable=set())
        return raw

    def test_out_of_range_unsized_comparisons_rejected_by_both_paths(self):
        # Verilog comparisons would extend, not turn 4 into zero. This narrow
        # frontend rejects that context instead of claiming to support it.
        for condition in ("u == 4", "4 == u", "u < 4", "4 > u", "u != 4"):
            source = source_for(condition)
            with self.subTest(condition=condition):
                with self.assertRaisesRegex(rtl_frontend.FrontendError, "unsized"):
                    self.translate(source)
                unrelated_ir = self.translate(source_for("u == 0"))
                with self.assertRaisesRegex(
                        rtl_translation_checker.TranslationValidationError, "unsized"):
                    rtl_translation_checker.validate_translation(
                        source, source.encode(), manifest(source, "u=0,1,2,3", "q=0"),
                        unrelated_ir, set())

    def test_logical_operands_are_self_determined(self):
        for condition, values in (
                ("u && 4", (0, 1, 1, 1)), ("4 && u", (0, 1, 1, 1)),
                ("u || 4", (1, 1, 1, 1)), ("!4", (0, 0, 0, 0)),
                ("u == 3", (0, 0, 0, 1)), ("u < 3", (1, 1, 1, 0))):
            source = source_for(condition)
            with self.subTest(condition=condition):
                raw = self.translate(source)
                result = rtl_translation_checker.validate_translation(
                    source, source.encode(), manifest(source, "u=0,1,2,3", "q=0"), raw, set())
                self.assertEqual(result["status"], "ACCEPT")
                pm, cm = producer.Model(raw), checker.Semantics(raw)
                for old_q in (0, 1):
                    for u, expected in enumerate(values):
                        _, pe = pm.observe((old_q,), (u,))
                        _, ce = cm.frame((old_q,), (u,), {})
                        self.assertEqual(pm.advance(pe), (expected,))
                        self.assertEqual(cm.next_state(ce, {}), (expected,))


if __name__ == "__main__":
    unittest.main()
