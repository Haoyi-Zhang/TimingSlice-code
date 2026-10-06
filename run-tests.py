#!/usr/bin/env python3
"""Run the standard-library regression suite and emit a machine-readable receipt."""
from __future__ import annotations

import argparse
import json
import sys
import time
import unittest
from pathlib import Path

from tests.support import COUNTS


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    started = time.perf_counter()
    suite = unittest.defaultTestLoader.discover(str(root / "tests"), pattern="test_*.py")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    historical_semantic_keys = {
        "operator_value_checks",
        "checker_semantic_obligations",
        "dynamic_negative_control_sample_checks",
        "accepted_translation_validations",
        "translation_binding_mutation_checks",
        "source_byte_substitution_checks",
    }
    repair_semantic_keys = {
        "detached_source_text_joint_substitution_checks",
        "external_cuttable_joint_substitution_checks",
        "source_case_translation_validations",
        "source_case_transition_contexts",
        "source_procedural_driver_rejections",
    }
    historical_semantic_units = sum(COUNTS[key] for key in historical_semantic_keys)
    repair_semantic_units = sum(COUNTS[key] for key in repair_semantic_keys)
    semantic_units = historical_semantic_units + repair_semantic_units
    report = {
        "status": "PASS" if result.wasSuccessful() else "FAIL",
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skipped": len(result.skipped),
        "wall_seconds": time.perf_counter() - started,
        "counts": dict(sorted(COUNTS.items())),
        "historical_regression_semantic_units": historical_semantic_units,
        "new_targeted_repair_semantic_units": repair_semantic_units,
        "semantic_units_this_run": semantic_units,
        "scope": "software regression including owned source-semantics fixtures; no minimization search or public workload selection",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
