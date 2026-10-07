"""Pure, owned paper-data gate regressions; no research programs are imported.

The fixture is independent synthetic evidence, not a retained implementation or
campaign copy. The optional --gate path permits a private actual-before check.
All audit inputs are in-memory; no files are created, deleted, or resealed.
"""
from __future__ import annotations

import argparse
import copy
import importlib.util
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "verify-paper-data.py"
CAMPAIGN = (
    "The retained campaign totals 150,022 units, including its source-validation "
    "probes and regressions, exceeding the 150,000 planning ceiling by 22 units."
)
CONTROL_LABELS = (
    ("joint-omission", "Joint omission"), ("zero-cancellation", "Zero cancellation"),
    ("post-completion", "Post-completion"), ("enable-counter", "Enable counter"),
    ("reset-counter", "Reset counter"), ("old-value-pipeline", "Old-value pipeline"),
    ("wrap-counter", "Wrap counter"), ("never-complete", "Never completes"),
    ("initial-completion", "Initially complete"), ("wire-width", "Wire width"),
    ("concat-slice", "Concat and slice"), ("shared-wire", "Shared wire"),
    ("minimum-gap", "Cardinality gap"),
)
RTL_ROWS = (
    ("cmos-counter-3", "CMOS counter", 4, 256, 1280),
    ("intro-counter-2", "Intro counter", 3, 64, 256),
    ("smt2-counter", "SMT2 self-reset", 4, 1, 5),
    ("verific-counter", "Verific counter", 4, 16, 80),
    ("smtbmc-demo4", "SMTBMC pair", 2, 256, 768),
    ("asic-up-counter-8", "ASIC up counter", 3, 64, 256),
    ("asic-up-down-8", "ASIC up/down", 3, 64, 256),
    ("asic-load-counter-8", "ASIC load counter", 2, 576, 1728),
    ("asic-tutorial-counter-4", "Tutorial counter", 3, 64, 256),
    ("sat-priority-counter-4", "SAT priority case", 4, 16, 80),
)


def independent_reference() -> dict[str, int]:
    # Independent direct arithmetic, including the original 83+19 correction.
    historical = sum((120045, 4538, 4538, 14422, 5803, 535, 16, 83, 19))
    executed = historical + 2 + sum((10, 8, 1, 1, 1))
    return {"historical_subtotal": historical, "executed_total": executed,
            "planning_ceiling": 150000, "overrun": executed - 150000}


def fixture(*, legacy_tokens: bool = False):
    artifact, project = Path("owned-artifact"), Path("owned-project")
    clean = artifact / "results" / "clean-reproduction"
    paper = project / "paper"
    accounting = {
        "core_campaign_semantic_work": 120045,
        "earlier_public_rtl_development_semantic_work": 4538,
        "earlier_public_rtl_clean_semantic_work": 4538,
        "expanded_public_rtl_generation_semantic_work": 14422,
        "expanded_public_rtl_clean_replay_semantic_work": 5803,
        "final_core_checker_replay_semantic_work": 535,
        "pre_release_small_checker_probe_semantic_work": 16,
        "software_regression_semantic_work": 102,
        "historical_campaign_after_accounting_correction": 149999,
        "translation_static_risk_pre_fix_semantic_work": 2,
        "translation_static_risk_post_fix_semantic_work": 21,
        "cumulative_semantic_work": 150022,
        "campaign_semantic_work_cap": 150000,
        "remaining_semantic_work": 0,
        "semantic_work_overrun": 22,
        "historical_large_search_repeated_for_repair": False,
        "ceiling_status": "EXCEEDED_BY_22_TARGETED_REPAIR_VALIDATIONS",
    }
    # Deliberately tiny frontier evidence, not real certificates or a replay.
    bundles = {name: {"frontiers": [[[]] * n for n in lengths]}
               for name, lengths in (("first", (1, 2, 0)), ("wave", (1, 2, 2)),
                                     ("unsliced", (1, 1, 0)))}
    jsons = {
        clean / "bundles/post-completion-first-hit.json": bundles["first"],
        clean / "bundles/post-completion-waveform.json": bundles["wave"],
        clean / "baselines/post-completion-unsliced-first-hit.json": bundles["unsliced"],
        artifact / "results/campaign-accounting.json": accounting,
        artifact / "results/bibliography-audit.json": {"status": "PASS", "entries": 56},
    }
    controls = [{"case": case, "observation": observer, "candidates": "1",
                 "retained": "1", "frontier_entries": "1", "preservation_obligations": "2"}
                for case, _ in CONTROL_LABELS for observer in ("first-hit", "waveform")]
    mutations = [{"mutation": f"owned-invalid-{i}", "expected_accepted": "False",
                  "accepted": "False", "reason": "owned invalid evidence"} for i in range(16)]
    mutations += [{"mutation": "sound-frontier-superset", "expected_accepted": "True",
                   "accepted": "True", "reason": "valid certificate"}]
    mutations += [{"mutation": name, "expected_accepted": "False", "accepted": "False",
                   "reason": "UNKNOWN, not a proof verdict"}
                  for name in ("checker-budget-zero", "producer-budget-zero")]
    csvs = {
        paper / "figures/frontiers.csv": [
            {"cycle": "0", "first_hit": "1", "waveform": "1", "unsliced_first_hit": "1"},
            {"cycle": "1", "first_hit": "2", "waveform": "2", "unsliced_first_hit": "1"},
            {"cycle": "2", "first_hit": "0", "waveform": "2", "unsliced_first_hit": "0"}],
        clean / "post_completion_baselines.csv": [
            {"configuration": name, "frontier_entries": str(count)} for name, count in
            (("sliced-first-hit", 3), ("sliced-waveform", 5), ("unsliced-first-hit", 2))],
        clean / "control_results.csv": controls,
        clean / "mutation_results.csv": mutations,
        artifact / "results/rtl-pilot/rtl_equivalence.csv": [
            {"case": case, "horizon": str(h), "traces": str(t), "samples": str(s)}
            for case, _, h, t, s in RTL_ROWS],
        artifact / "results/rtl-pilot/rtl_slice_bundles.csv": [{"case": RTL_ROWS[0][0]}],
    }
    texts = {
        paper / "main.tex": (
            "Sixteen invalid evidence mutations are rejected, a sound frontier superset "
            "is accepted, and two zero-budget controls return UNKNOWN. " + CAMPAIGN +
            (" Historical tokens: 149,999; 150,022; 22 above." if legacy_tokens else "")),
        paper / "control-table.tex": "\n".join(
            label + " & 1 & 1 & 1 & 1 & 1 & 2 & 2 \\\\" for _, label in CONTROL_LABELS),
        paper / "rtl-table.tex": "\n".join(
            label + ("$^*$" if i == 0 else "") + f" & {h} & {t:,} & {s:,}"
            for i, (_, label, h, t, s) in enumerate(RTL_ROWS)) +
            "\nTotal: 10 modules, 1,377 traces, 4,965 samples",
    }
    return artifact, project, jsons, csvs, texts


class PaperDataRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("owned_paper_data_gate", GATE)
        if spec is None or spec.loader is None:
            raise ImportError(GATE)
        cls.gate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.gate)

    def audit(self, data):
        artifact, project, jsons, csvs, texts = data
        def read_text(path, *args, **kwargs):
            return texts[path]
        with mock.patch.object(self.gate, "read_json", side_effect=lambda p: copy.deepcopy(jsons[p])), \
             mock.patch.object(self.gate, "read_csv", side_effect=lambda p: copy.deepcopy(csvs[p])), \
             mock.patch.object(Path, "read_text", read_text):
            return self.gate.audit(artifact, project)

    def test_current_sentence_without_obsolete_tokens(self):
        data = fixture()
        self.assertNotIn("149,999", data[4][data[1] / "paper/main.tex"])
        report = self.audit(data)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["retained_campaign_accounting"], independent_reference())
        self.assertFalse(report["scientific_search_repeated"])
        self.assertEqual((report["figure_3_points_checked"], report["control_table_rows_checked"],
                          report["public_rtl_rows_checked"]), (9, 13, 10))
        self.assertEqual(report["certificate_controls"], {
            "invalid_rejected": 16, "sound_superset_accepted": 1, "unknown_budget_controls": 2})

    def test_numeric_accounting_faults_even_with_legacy_tokens(self):
        original = fixture(legacy_tokens=True)
        path = original[0] / "results/campaign-accounting.json"
        for field, value in original[2][path].items():
            if type(value) is not int:
                continue
            for bad in (value + 1, float(value), str(value), False, None):
                with self.subTest(field=field, bad=bad):
                    data = copy.deepcopy(original)
                    data[2][path][field] = bad
                    with self.assertRaises(self.gate.PaperDataError):
                        self.audit(data)
        data = copy.deepcopy(original)
        data[2][path]["core_campaign_semantic_work"] += 1
        data[2][path]["earlier_public_rtl_clean_semantic_work"] -= 1
        with self.assertRaises(self.gate.PaperDataError):
            self.audit(data)

    def test_repair_boundary_and_missing_metadata_rejected(self):
        for field, bad in (("historical_large_search_repeated_for_repair", True),
                           ("historical_large_search_repeated_for_repair", 0),
                           ("ceiling_status", "WITHIN_CAP")):
            data = fixture(legacy_tokens=True)
            data[2][data[0] / "results/campaign-accounting.json"][field] = bad
            with self.subTest(field=field, bad=bad), self.assertRaises(self.gate.PaperDataError):
                self.audit(data)
        data = fixture(legacy_tokens=True)
        data[2][data[0] / "results/campaign-accounting.json"] = []
        with self.assertRaises(self.gate.PaperDataError):
            self.audit(data)
        data = fixture(legacy_tokens=True)
        del data[2][data[0] / "results/campaign-accounting.json"]["cumulative_semantic_work"]
        with self.assertRaises(self.gate.PaperDataError):
            self.audit(data)

    def test_legacy_tokens_do_not_mask_wrong_current_statement(self):
        for old, new in (("totals 150,022", "totals 149,999"),
                         ("the 150,000 planning", "the 150,001 planning"),
                         ("by 22 units", "by 0 units"),
                         ("exceeding", "not exceeding")):
            data = fixture(legacy_tokens=True)
            path = data[1] / "paper/main.tex"
            data[4][path] = data[4][path].replace(old, new)
            with self.subTest(new=new), self.assertRaises(self.gate.PaperDataError):
                self.audit(data)

    def test_existing_mutation_and_unknown_counts_stay_strict(self):
        for index in range(19):
            data = fixture(legacy_tokens=True)
            row = data[3][data[0] / "results/clean-reproduction/mutation_results.csv"][index]
            if index < 16:
                row["accepted"] = "True"
            elif index == 16:
                row["accepted"] = "False"
            else:
                row["reason"] = "Rejected, not UNKNOWN"
            with self.subTest(index=index), self.assertRaises(self.gate.PaperDataError):
                self.audit(data)

    def test_existing_figure_and_table_checks_stay_strict(self):
        faults = (
            ("csv", "paper/figures/frontiers.csv", "first_hit"),
            ("csv", "artifact/results/clean-reproduction/post_completion_baselines.csv", "frontier_entries"),
            ("csv", "artifact/results/clean-reproduction/control_results.csv", "retained"),
            ("csv", "artifact/results/rtl-pilot/rtl_equivalence.csv", "samples"),
            ("text", "paper/control-table.tex", "Joint omission"),
            ("text", "paper/rtl-table.tex", "Total: 10 modules"),
        )
        for kind, relative, field in faults:
            data = fixture(legacy_tokens=True)
            base = data[1] if relative.startswith("paper/") else data[0]
            path = base / (relative if relative.startswith("paper/") else relative[9:])
            if kind == "csv":
                data[3][path][0][field] = "9999"
            else:
                data[4][path] = data[4][path].replace(field, "owned corrupted display")
            with self.subTest(relative=relative), self.assertRaises(self.gate.PaperDataError):
                self.audit(data)

    def test_existing_bibliography_gate_stays_strict(self):
        for bad in ({"status": "FAIL", "entries": 56}, {"status": "PASS", "entries": 55}):
            data = fixture(legacy_tokens=True)
            data[2][data[0] / "results/bibliography-audit.json"] = bad
            with self.subTest(bad=bad), self.assertRaises(self.gate.PaperDataError):
                self.audit(data)

    def test_tex_whitespace_does_not_change_accounting(self):
        data = fixture()
        path = data[1] / "paper/main.tex"
        data[4][path] = data[4][path].replace(" ", "\n\t").replace(",", "\\,")
        self.assertEqual(self.audit(data)["retained_campaign_accounting"], independent_reference())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gate", type=Path, default=GATE)
    args, rest = parser.parse_known_args()
    GATE = args.gate
    unittest.main(argv=[sys.argv[0], *rest], verbosity=2)
