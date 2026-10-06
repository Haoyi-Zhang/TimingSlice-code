"""Narrow finite regressions for case selection and procedural ownership."""
from __future__ import annotations

import hashlib
import itertools
import unittest

from src import checker, producer, rtl_frontend, rtl_translation_checker
from tests.support import record


def manifest(source: str, domains: str, initial: str) -> dict[str, str]:
    payload = source.encode("utf-8")
    return {"case_id": "owned-source-regression", "module": "owned", "clock": "clk",
            "horizon": "1", "input_domains": domains, "initial_state": initial,
            "done_expression": "q", "cuttable": "",
            "blob_sha": hashlib.sha1(f"blob {len(payload)}\0".encode() + payload).hexdigest()}


def translate(source: str, domains: dict[str, list[int]], initial: dict[str, int]) -> dict:
    raw, _ = rtl_frontend.translate(
        source, module_name="owned", model_id="owned-source-regression", clock="clk",
        done_expression="q", horizon=1, domains=domains, initial_state=initial, cuttable=set(),
    )
    return raw


class SourceSelectionTests(unittest.TestCase):
    def check_all_states(self, source: str, domains: dict[str, list[int]], oracle) -> None:
        # The direct formulas below use neither source parser nor IR evaluator.
        initial = {name: 0 for name in ("p", "q") if f"reg {name}" in source or name == "q"}
        raw = translate(source, domains, initial)
        row = manifest(source, ";".join(f"{key}=" + ",".join(map(str, values))
                                       for key, values in domains.items()),
                       ";".join(f"{key}=0" for key in initial))
        result = rtl_translation_checker.validate_translation(
            source, source.encode(), row, raw, set())
        self.assertEqual(result["status"], "ACCEPT")
        record("source_case_translation_validations", 1)
        pmodel, cmodel = producer.Model(raw), checker.Semantics(raw)
        names = [item["name"] for item in raw["registers"]]
        input_names = [item["name"] for item in raw["inputs"]]
        contexts = 0
        for state in itertools.product((0, 1), repeat=len(names)):
            for inputs in pmodel.inputs():
                state_map, input_map = dict(zip(names, state)), dict(zip(input_names, inputs))
                expected = oracle(state_map, input_map)
                dp, ep = pmodel.observe(state, inputs)
                dc, ec = cmodel.frame(state, inputs, {})
                self.assertEqual((dp, dict(zip(names, pmodel.advance(ep)))), (state_map["q"], expected))
                self.assertEqual((dc, dict(zip(names, cmodel.next_state(ec, {})))), (state_map["q"], expected))
                contexts += 1
        record("source_case_transition_contexts", contexts)

    def test_default_first_middle_and_last_preserve_selection_and_holds(self) -> None:
        branches = ["2'd0: p <= 1'b1;", "2'd1: q <= 1'b0;"]
        for position in range(3):
            ordered = list(branches)
            ordered.insert(position, "default: q <= 1'b1;")
            source = ("module owned(input clk, input [1:0] sel, output reg q, output reg p);\n"
                      "always @(posedge clk) begin case (sel)\n" + "\n".join(ordered) +
                      "\nendcase end\nendmodule\n")
            with self.subTest(position=position):
                self.check_all_states(source, {"sel": [0, 1, 2, 3]},
                    lambda s, u: {"p": 1 if u["sel"] == 0 else s["p"],
                                  "q": s["q"] if u["sel"] == 0 else int(u["sel"] != 1)})

    def test_nested_if_inside_early_default_keeps_outer_case_guard(self) -> None:
        source = """module owned(input clk, input sel, input gate, output reg q, output reg p);
always @(posedge clk) begin
 case (sel)
 default: if (gate) q <= 1'b1; else q <= 1'b0;
 1'b0: p <= 1'b1;
 endcase
end
endmodule
"""
        self.check_all_states(source, {"sel": [0, 1], "gate": [0, 1]},
            lambda s, u: {"p": s["p"] if u["sel"] else 1,
                          "q": u["gate"] if u["sel"] else s["q"]})

    def test_two_blocks_driving_one_register_are_rejected_by_both_paths(self) -> None:
        source = """module owned(input clk, output reg q);
always @(posedge clk) q <= 1'b0;
always @(posedge clk) q <= 1'b1;
endmodule
"""
        with self.assertRaisesRegex(rtl_frontend.FrontendError, "procedural"):
            translate(source, {}, {"q": 0})
        record("source_procedural_driver_rejections", 1)
        # Supply the previously accepted last-block-wins IR directly: the
        # validator must reject the source without relying on the translator.
        raw = {"id": "owned-source-regression", "inputs": [], "wires": [], "horizon": 1,
               "registers": [{"name": "q", "width": 1, "init": 0, "cut": False,
                              "next": ["mux", ["const", 1, 1], ["const", 1, 1],
                                       ["mux", ["const", 1, 1], ["const", 1, 0], ["var", "q"]]]}],
               "done": ["var", "q"]}
        with self.assertRaisesRegex(rtl_translation_checker.TranslationValidationError, "procedural"):
            rtl_translation_checker.validate_translation(
                source, source.encode(), manifest(source, "", "q=0"), raw, set())
        record("source_procedural_driver_rejections", 1)

    def test_last_nonblocking_assignment_within_one_block_still_wins(self) -> None:
        source = """module owned(input clk, output reg q);
always @(posedge clk) begin q <= 1'b0; q <= 1'b1; end
endmodule
"""
        self.check_all_states(source, {}, lambda s, u: {"q": 1})

    def test_separate_blocks_with_disjoint_targets_are_allowed(self) -> None:
        source = """module owned(input clk, output reg q, output reg p);
always @(posedge clk) q <= p;
always @(posedge clk) p <= ~p;
endmodule
"""
        self.check_all_states(source, {}, lambda s, u: {"q": s["p"], "p": 1 - s["p"]})

    def test_first_matching_explicit_label_retains_priority(self) -> None:
        source = """module owned(input clk, input [1:0] sel, output reg q);
always @(posedge clk) case (sel)
 default: q <= 1'b1;
 2'd0: q <= 1'b0;
 2'd0: q <= 1'b1;
endcase
endmodule
"""
        self.check_all_states(source, {"sel": [0, 1, 2, 3]},
                              lambda s, u: {"q": int(u["sel"] != 0)})


if __name__ == "__main__":
    unittest.main()
