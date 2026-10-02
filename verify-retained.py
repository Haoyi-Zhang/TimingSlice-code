#!/usr/bin/env python3
"""Statically audit retained result closure without repeating scientific search."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


class AuditError(RuntimeError):
    pass


def load_json(path: Path):
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise AuditError(f"cannot read {path}: {error}") from error


def count_csv(path: Path) -> int:
    try:
        with path.open(newline="") as handle:
            return sum(1 for _ in csv.DictReader(handle))
    except OSError as error:
        raise AuditError(f"cannot read {path}: {error}") from error


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AuditError(message)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent

    core = load_json(root / "results" / "clean-reproduction" / "summary.json")
    require(core.get("pilot_status") == "PASS", "retained core status is not PASS")
    require(core.get("research_gate") == "HOLD", "retained core gate changed")
    expected_core = {
        "unique_generated_models": 109,
        "reduction_subset_queries": 928,
        "canonical_control_witnesses_checked": 35,
        "closed_form_transition_pairs": 5401,
        "operator_value_checks": 2410,
        "invalid_mutations_rejected": 16,
        "unknown_budget_controls": 2,
    }
    for key, value in expected_core.items():
        require(core.get(key) == value, f"retained core count mismatch: {key}")
    require(len(list((root / "cases").glob("*.json"))) == 109, "fixture count is not 109")
    require(count_csv(root / "results" / "clean-reproduction" / "control_results.csv") == 26,
            "control result count is not 26")
    require(count_csv(root / "results" / "clean-reproduction" / "reduction_conditions.csv") == 96,
            "reduction condition count is not 96")

    public = load_json(root / "results" / "rtl-pilot" / "summary.json")
    expected_public = {
        "status": "PASS",
        "mode": "generate",
        "public_rtl_modules": 10,
        "source_blobs_independently_verified": 10,
        "full_state_and_done_sample_checks": 4965,
        "first_completion_bundles_checked": 4,
        "dynamic_translation_mutations_detected": 3,
        "translation_binding_mutations_rejected": 8,
        "total_semantic_units": 14422,
    }
    for key, value in expected_public.items():
        require(public.get(key) == value, f"retained RTL result mismatch: {key}")
    require(count_csv(root / "public_rtl" / "yosys" / "manifest.csv") == 10,
            "public RTL manifest count is not 10")
    require(count_csv(root / "results" / "rtl-pilot" / "rtl_equivalence.csv") == 10,
            "RTL equivalence row count is not 10")
    require(count_csv(root / "results" / "rtl-pilot" / "translation_validation.csv") == 10,
            "translation-validation row count is not 10")
    require(count_csv(root / "results" / "rtl-pilot" / "translation_validation_mutations.csv") == 8,
            "translation mutation count is not 8")
    bundles = sorted((root / "results" / "rtl-pilot" / "bundles").glob("*.json"))
    require(len(bundles) == 4, "retained public bundle count is not 4")
    for bundle_path in bundles:
        bundle = load_json(bundle_path)
        require(bundle.get("status") == "inclusion-minimal",
                f"retained bundle is not inclusion-minimal: {bundle_path.name}")

    accounting = load_json(root / "results" / "campaign-accounting.json")
    require(accounting.get("historical_campaign_after_accounting_correction") == 149999,
            "corrected historical accounting is not 149999")
    require(accounting.get("cumulative_semantic_work") == 150022,
            "final cumulative accounting is not 150022")
    require(accounting.get("remaining_semantic_work") == 0,
            "final remaining accounting is not zero")
    require(accounting.get("semantic_work_overrun") == 22,
            "final accounting does not expose the 22-unit repair overrun")
    require(accounting.get("software_regression_semantic_work") == 102,
            "corrected retained regression accounting is not 102")

    pre_fix = load_json(root / "results" / "translation-static-risk-pre-fix.json")
    require(pre_fix.get("results", {}).get(
        "source_text_source_bytes_joint_substitution", {}).get("outcome") == "ACCEPT",
        "pre-fix detached-text risk was not truthfully retained")
    require(pre_fix.get("results", {}).get(
        "external_cuttable_joint_substitution", {}).get("outcome") == "ACCEPT",
        "pre-fix cuttable risk was not truthfully retained")
    post_fix = load_json(root / "results" / "translation-static-risk-postfix.json")
    require(post_fix.get("status") == "PASS" and post_fix.get("semantic_units_this_run") == 21,
            "post-fix targeted translation receipt is not PASS/21")
    counts = post_fix.get("counts", {})
    require(counts.get("accepted_translation_validations") == 10,
            "post-fix normal translation acceptance count is not 10")
    require(counts.get("translation_binding_mutation_checks") == 8,
            "post-fix retained binding-mutation count is not 8")
    require(counts.get("source_byte_substitution_checks") == 1,
            "post-fix source-byte substitution count is not 1")
    require(counts.get("detached_source_text_joint_substitution_checks") == 1,
            "post-fix detached-text joint check is missing")
    require(counts.get("external_cuttable_joint_substitution_checks") == 1,
            "post-fix cuttable joint check is missing")

    report = {
        "status": "PASS",
        "scientific_search_repeated": False,
        "core_fixture_files": 109,
        "core_retained_summary_verified": expected_core,
        "public_manifest_rows": 10,
        "public_translation_rows": 10,
        "public_retained_bundles": 4,
        "software_regression_tests": 19,
        "software_regression_semantic_units": 102,
        "post_fix_targeted_test_methods": 5,
        "post_fix_targeted_semantic_units": 21,
        "final_cumulative_semantic_work": 150022,
        "semantic_work_overrun": 22,
        "boundary": "static closure audit only; mathematical and semantic claims rely on retained runs",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
