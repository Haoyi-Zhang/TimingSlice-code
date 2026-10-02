from __future__ import annotations

import copy
import csv
import hashlib
import json
import unittest
from pathlib import Path

from src import producer, rtl_frontend, rtl_translation_checker
from tests.support import load_script, record

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public_rtl" / "yosys"
RTL_PILOT = load_script(ROOT / "rtl-pilot.py", "pcds_rtl_pilot_for_tests")


def manifest_rows() -> list[dict[str, str]]:
    with (PUBLIC / "manifest.csv").open(newline="") as handle:
        return list(csv.DictReader(handle))


def translate(item: dict[str, str]) -> tuple[str, bytes, dict]:
    source_path = PUBLIC / item["path"]
    source_bytes = source_path.read_bytes()
    source_text = source_bytes.decode("utf-8")
    raw, _ = rtl_frontend.translate(
        source_text,
        module_name=item["module"],
        model_id=item["case_id"],
        clock=item["clock"],
        done_expression=item["done_expression"],
        horizon=int(item["horizon"]),
        domains=RTL_PILOT.parse_domains(item["input_domains"]),
        initial_state=RTL_PILOT.parse_state(item["initial_state"]),
        cuttable=RTL_PILOT.parse_cuttable(item["cuttable"]),
    )
    producer.Model(raw)
    return source_text, source_bytes, raw


class RestrictedRTLTests(unittest.TestCase):
    def test_all_pinned_blobs_and_translations_validate(self) -> None:
        rows = manifest_rows()
        self.assertEqual(len(rows), 10)
        structural = 0
        seen_cases = set()
        for item in rows:
            with self.subTest(case=item["case_id"]):
                self.assertNotIn(item["case_id"], seen_cases)
                seen_cases.add(item["case_id"])
                source_text, source_bytes, raw = translate(item)
                header = f"blob {len(source_bytes)}\0".encode("ascii")
                self.assertEqual(hashlib.sha1(header + source_bytes).hexdigest(), item["blob_sha"])
                result = rtl_translation_checker.validate_translation(
                    source_text,
                    source_bytes,
                    item,
                    raw,
                    RTL_PILOT.parse_cuttable(item["cuttable"]),
                )
                self.assertEqual(result["status"], "ACCEPT")
                self.assertTrue(result["source_blob_verified"])
                structural += int(result["structural_comparison_units"])
        self.assertEqual(structural, 601)
        record("accepted_translation_validations", len(rows))
        record("structural_translation_comparison_units", structural)

    def test_eight_binding_mutations_are_rejected(self) -> None:
        sources = {}
        raw_by_case = {}
        cut_by_case = {}
        for item in manifest_rows():
            source_text, source_bytes, raw = translate(item)
            case = item["case_id"]
            sources[case] = (source_text, source_bytes, item)
            raw_by_case[case] = raw
            cut_by_case[case] = RTL_PILOT.parse_cuttable(item["cuttable"])
        results = RTL_PILOT.translation_negative_controls(sources, raw_by_case, cut_by_case)
        self.assertEqual(len(results), 8)
        self.assertTrue(all(row["independent_validator_rejected"] for row in results))
        record("translation_binding_mutation_checks", len(results))

    def test_three_dynamic_mistranslations_are_detected(self) -> None:
        raw_by_case = {}
        for item in manifest_rows():
            _, _, raw = translate(item)
            raw_by_case[item["case_id"]] = raw
        rows = RTL_PILOT.dynamic_negative_controls(raw_by_case)
        self.assertEqual([row["paired_samples_to_detection"] for row in rows], [2, 2, 51])
        self.assertTrue(all(row["oracle_detected"] for row in rows))
        record("dynamic_negative_control_sample_checks",
               sum(int(row["paired_samples_to_detection"]) for row in rows))

    def test_manifest_scope_and_license_are_explicit(self) -> None:
        rows = manifest_rows()
        self.assertTrue(all(row["repository"] == "YosysHQ/yosys" for row in rows))
        self.assertEqual({row["commit"] for row in rows},
                         {"d0e71cfb7bcafe2b437f3edc1789b69e99ecd55a"})
        license_text = (PUBLIC / "LICENSE-ISC.txt").read_text()
        self.assertIn("ISC License", license_text)
        self.assertIn("Permission to use, copy, modify", license_text)

    def test_validator_rejects_source_byte_substitution(self) -> None:
        item = copy.deepcopy(manifest_rows()[0])
        source_text, source_bytes, raw = translate(item)
        modified = source_bytes + b"\n"
        with self.assertRaises(rtl_translation_checker.TranslationValidationError):
            rtl_translation_checker.validate_translation(
                source_text + "\n", modified, item, raw,
                RTL_PILOT.parse_cuttable(item["cuttable"]),
            )
        record("source_byte_substitution_checks", 1)

    def test_validator_rejects_detached_source_text_with_matching_ir(self) -> None:
        """Changing detached text and IR cannot inherit the real source-byte hash."""
        item = copy.deepcopy(next(row for row in manifest_rows()
                                  if row["case_id"] == "cmos-counter-3"))
        source_text, source_bytes, raw = translate(item)
        changed_text = source_text.replace("count + 3'd1", "count + 3'd2")
        changed_raw = copy.deepcopy(raw)
        changed_raw["registers"][0]["next"][2][2] = ["const", 3, 2]
        with self.assertRaises(rtl_translation_checker.TranslationValidationError):
            rtl_translation_checker.validate_translation(
                changed_text,
                source_bytes,
                item,
                changed_raw,
                RTL_PILOT.parse_cuttable(item["cuttable"]),
            )
        record("detached_source_text_joint_substitution_checks", 1)

    def test_validator_rejects_external_cuttable_with_matching_ir(self) -> None:
        """The manifest candidate universe cannot be replaced by caller policy plus IR."""
        item = copy.deepcopy(next(row for row in manifest_rows()
                                  if row["case_id"] == "cmos-counter-3"))
        source_text, source_bytes, raw = translate(item)
        changed_raw = copy.deepcopy(raw)
        changed_raw["registers"][0]["cut"] = False
        with self.assertRaises(rtl_translation_checker.TranslationValidationError):
            rtl_translation_checker.validate_translation(
                source_text,
                source_bytes,
                item,
                changed_raw,
                set(),
            )
        record("external_cuttable_joint_substitution_checks", 1)


if __name__ == "__main__":
    unittest.main()
