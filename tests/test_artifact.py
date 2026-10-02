from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ArtifactClosureTests(unittest.TestCase):
    def test_required_standalone_files_exist(self) -> None:
        required = {
            "README.md", "LICENSE", "ir-contract.md", "rtl-subset.md",
            "pilot-protocol.md", "reproduce.py", "rtl-pilot.py",
            "verify-retained.py", "claim_evidence_ledger.csv",
            "external_resources.csv", "literature-calibration.csv",
        }
        self.assertTrue(required <= {p.name for p in ROOT.iterdir()})
        for directory in ("src", "tests", "cases", "proofs", "results", "public_rtl"):
            self.assertTrue((ROOT / directory).is_dir(), directory)

    def test_retained_static_audit_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "audit.json"
            completed = subprocess.run(
                [sys.executable, str(ROOT / "verify-retained.py"), "--out", str(out)],
                cwd=ROOT, capture_output=True, text=True, check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            report = json.loads(out.read_text())
            self.assertEqual(report["status"], "PASS")
            self.assertFalse(report["scientific_search_repeated"])

    def test_retained_mutation_receipts_have_expected_outcomes(self) -> None:
        with (ROOT / "results" / "clean-reproduction" / "mutation_results.csv").open(newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 19)
        invalid = [r for r in rows if r["mutation"] not in {
            "sound-frontier-superset", "checker-budget-zero", "producer-budget-zero"
        }]
        self.assertEqual(len(invalid), 16)
        self.assertTrue(all(r["accepted"] == "False" for r in invalid))
        superset = next(r for r in rows if r["mutation"] == "sound-frontier-superset")
        self.assertEqual(superset["accepted"], "True")

    def test_claim_ledger_has_evidence_and_maturity_for_every_row(self) -> None:
        with (ROOT / "claim_evidence_ledger.csv").open(newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertGreaterEqual(len(rows), 20)
        for row in rows:
            self.assertTrue(row.get("claim_id"), row)
            self.assertTrue(row.get("claim"), row)
            self.assertTrue(row.get("maturity"), row)
            self.assertTrue(row.get("raw_evidence"), row)

    def test_no_nested_archive_is_shipped(self) -> None:
        archives = [path.relative_to(ROOT).as_posix() for path in ROOT.rglob("*.zip")]
        self.assertEqual(archives, [])


if __name__ == "__main__":
    unittest.main()
