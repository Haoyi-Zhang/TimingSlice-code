"""Bibliography consumers distinguish scholarly entries from style settings."""
from __future__ import annotations

import csv
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("bibliography_under_test", ROOT / "audit-bibliography.py")
AUDIT = importlib.util.module_from_spec(SPEC)
if SPEC.loader is None:
    raise RuntimeError("bibliography module loader unavailable")
SPEC.loader.exec_module(AUDIT)


class BibliographyTests(unittest.TestCase):
    def run_generator(self, root: Path) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, "-B", str(ROOT / "audit-bibliography.py"),
            "--tex", str(root / "main.tex"), "--bib", str(root / "references.bib"),
            "--calibration", str(root / "calibration.csv"), "--out", str(root / "audit.csv"),
            "--summary", str(root / "summary.json")], capture_output=True)

    def test_ieee_style_control_is_not_a_scholarly_entry(self) -> None:
        self.assertEqual(AUDIT.entries("@IEEEtranBSTCTL{settings,\n CTLdash_repeated_names={no}\n}"), [])

    def test_scholarly_key_named_like_a_style_control_is_preserved(self) -> None:
        self.assertEqual(AUDIT.entries("@article{authorDisplay,\n title={Study}\n}")[0][:2],
                         ("article", "authorDisplay"))

    def test_full_generator_preserves_utf8_and_excludes_style_controls(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            keys = [f"study{i}" for i in range(55)]
            bib = "@IEEEtranBSTCTL{settings,\n CTLdash_repeated_names={no}\n}\n"
            for key in keys:
                bib += (f"@article{{{key},\n author={{\u00c9mile Researcher}},\n"
                        " title={\u00c9tude},\n year={2020},\n journal={Journal}\n}\n")
            (root / "references.bib").write_text(bib, encoding="utf-8")
            (root / "main.tex").write_text("\\cite{" + ",".join(keys) + "}", encoding="utf-8")
            (root / "calibration.csv").write_text("bibkey\n", encoding="utf-8")
            result = self.run_generator(root)
            self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", errors="replace"))
            with (root / "audit.csv").open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 55)
            self.assertEqual(rows[0]["author"], "\u00c9mile Researcher")
            self.assertEqual(rows[0]["title"], "\u00c9tude")
            self.assertEqual(json.loads((root / "summary.json").read_text(encoding="utf-8"))["entries"], 55)

    def test_comment_citations_do_not_change_active_reference_closure(self) -> None:
        keys = [f"study{i}" for i in range(55)]
        cases = [(keys[:-1], r"% note: \cite{study54}", 1),
                 (keys, r"% note: \cite{missing}", 0),
                 (keys[:-1], r"\% escaped percent, active \cite{study54}", 0),
                 (keys[:-1], r"Text\\% comment-only \cite{study54}", 1),
                 (keys[:-1], r"Text\\\% escaped percent, active \cite{study54}", 0)]
        for active, suffix, code in cases:
            with self.subTest(suffix=suffix), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                bib = "".join(f"@article{{{key},\n author={{A. Researcher}},\n title={{Study {key}}},\n"
                              " year={2020},\n journal={Journal}\n}\n" for key in keys)
                (root / "references.bib").write_text(bib, encoding="utf-8")
                (root / "main.tex").write_text("\\cite{" + ",".join(active) + "}\n" + suffix, encoding="utf-8")
                (root / "calibration.csv").write_text("bibkey\n", encoding="utf-8")
                result = self.run_generator(root)
                self.assertEqual(result.returncode, code, result.stderr.decode("utf-8", errors="replace"))
                summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))
                if code:
                    self.assertIn("uncited BibTeX entries", summary["reason"])
                else:
                    self.assertEqual(summary["cited_entries"], 55)


if __name__ == "__main__":
    unittest.main()
