"""Benign regression fixtures for the current manuscript-release consumer."""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("release_layout_under_test", ROOT / "verify-release.py")
AUDIT = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(AUDIT)


class CurrentPaperReleaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        self.paper, self.artifact = self.project / "paper", self.project / "artifact"
        self.paper.mkdir()
        self.artifact.mkdir()
        (self.paper / "figures").mkdir()
        self.keys = [f"source{i}" for i in range(56)]
        references = ["@IEEEtranBSTCTL{authorDisplay,\n CTLdash_repeated_names={no}\n}\n"]
        for key in self.keys:
            references.append(f"@article{{{key},\n author={{A. Researcher}},\n title={{A relevant source}},\n year={{2020}},\n journal={{Journal}}\n}}\n")
        (self.paper / "references.bib").write_text("".join(references), encoding="utf-8")
        tex = ("\\begin{abstract}" + " ".join(["word"] * 120) + "\\end{abstract}\n"
               "\\begin{IEEEkeywords}one,two,three,four\\end{IEEEkeywords}\n"
               "".join("\\section{Section}\n" for _ in range(7)) +
               "".join("\\cite{" + key + "}\n" for key in self.keys))
        (self.paper / "main.tex").write_text(tex, encoding="utf-8")
        (self.paper / "main.pdf").write_bytes(b"current-pdf-fixture")
        (self.paper / "main.log").write_text("clean build\n", encoding="utf-8")
        (self.paper / "main.aux").write_text("\\citation{authorDisplay}\n" +
            "".join("\\citation{" + key + "}\n" for key in self.keys), encoding="utf-8")
        (self.paper / "main.bbl").write_text("".join("\\bibitem{" + key + "} entry\n" for key in self.keys), encoding="utf-8")
        for name in ("observer", "pipeline", "frontiers"):
            (self.paper / "figures" / (name + ".tex")).write_text("figure\n", encoding="utf-8")
        (self.paper / "figures/frontiers.pdf").write_bytes(b"vector-figure-fixture")
        for name in ("control", "rtl", "certificate"):
            (self.paper / (name + "-table.tex")).write_text("table\n", encoding="utf-8")
        self.pages = 12
        self.embedded = "yes"
        self.called_pdfs: list[str] = []
        self.called_commands: list[tuple[str, ...]] = []

    def command(self, name: str, pdf: str, *args: str) -> str:
        self.called_pdfs.append(Path(pdf).name)
        self.called_commands.append((name, pdf, *args))
        if name == "pdfinfo":
            return f"Pages: {self.pages}\nPage size: 612 x 792 pts\n"
        if name == "pdffonts":
            return "name type encoding emb sub uni object ID\n----------------\n" + \
                f"ABCDEF+Times Type1 WinAnsi {self.embedded} yes yes 5 0\n"
        if name == "pdftotext":
            return "Proof-Carrying Bounded Dependency Slices REFERENCES"
        raise AssertionError(name)

    def test_current_pdf_and_bibliography_style_control_are_accepted(self) -> None:
        with patch.object(AUDIT, "command", self.command):
            result = AUDIT.audit_paper(self.paper)
        self.assertEqual(result["pdf"], "main.pdf")
        self.assertEqual(result["bibliography_entries"], 56)
        self.assertTrue(result["current_compiled_citations_match"])
        self.assertEqual(set(self.called_pdfs), {"main.pdf"})
        self.assertIn(("pdfinfo", str(self.paper / "main.pdf"), "-enc", "UTF-8", "-rawdates"),
                      self.called_commands)

    def test_legacy_only_pdf_is_not_a_current_manuscript(self) -> None:
        (self.paper / "main.pdf").rename(self.paper / "paper.pdf")
        with patch.object(AUDIT, "command", self.command), self.assertRaises(AUDIT.ReleaseAuditError):
            AUDIT.audit_paper(self.paper)

    def test_two_different_manuscript_copies_are_rejected(self) -> None:
        (self.paper / "paper.pdf").write_bytes(b"obsolete-pdf-fixture")
        with patch.object(AUDIT, "command", self.command), self.assertRaisesRegex(AUDIT.ReleaseAuditError, "redundant"):
            AUDIT.audit_paper(self.paper)

    def test_current_two_directory_project_needs_no_private_plans(self) -> None:
        result = AUDIT.audit_project(self.project, self.artifact)
        self.assertEqual(result["root_entries"], ["artifact", "paper"])
        (self.project / "README.md").write_text("Optional project overview\n", encoding="utf-8")
        self.assertEqual(AUDIT.audit_project(self.project, self.artifact)["status"], "PASS")

    def test_subset_flag_cannot_hide_an_unembedded_font(self) -> None:
        self.embedded = "no"
        with patch.object(AUDIT, "command", self.command), self.assertRaisesRegex(AUDIT.ReleaseAuditError, "unembedded"):
            AUDIT.audit_paper(self.paper)

    def test_public_page_limit_is_not_a_frozen_twelve_page_target(self) -> None:
        self.pages = 13
        with patch.object(AUDIT, "command", self.command):
            self.assertEqual(AUDIT.audit_paper(self.paper)["pages"], 13)
        self.pages = 15
        with patch.object(AUDIT, "command", self.command), self.assertRaisesRegex(AUDIT.ReleaseAuditError, "14-page"):
            AUDIT.audit_paper(self.paper)

    def test_current_pdf_must_equal_supplied_build_product(self) -> None:
        build = self.project / "isolated-build"
        build.mkdir()
        (build / "main.pdf").write_bytes(b"different-build-fixture")
        with patch.object(AUDIT, "command", self.command), self.assertRaisesRegex(AUDIT.ReleaseAuditError, "differs"):
            AUDIT.audit_paper(self.paper, build)

    def test_separate_current_build_supplies_log_and_citation_products(self) -> None:
        build = self.project / "isolated-build"
        build.mkdir()
        (build / "main.pdf").write_bytes((self.paper / "main.pdf").read_bytes())
        for name in ("main.log", "main.aux", "main.bbl"):
            (self.paper / name).rename(build / name)
        with patch.object(AUDIT, "command", self.command):
            self.assertTrue(AUDIT.audit_paper(self.paper, build)["current_build_pdf_matches"])
        (build / "main.aux").write_text("\\citation{source0}\n", encoding="utf-8")
        with patch.object(AUDIT, "command", self.command), self.assertRaisesRegex(AUDIT.ReleaseAuditError, "citations differ"):
            AUDIT.audit_paper(self.paper, build)

    def test_stale_compiled_citations_are_rejected(self) -> None:
        (self.paper / "main.aux").write_text("\\citation{source0}\n", encoding="utf-8")
        with patch.object(AUDIT, "command", self.command), self.assertRaisesRegex(AUDIT.ReleaseAuditError, "citations differ"):
            AUDIT.audit_paper(self.paper)

    def test_tex_comment_escape_parity_preserves_live_citations(self) -> None:
        original = (self.paper / "main.tex").read_text(encoding="utf-8")
        (self.paper / "main.tex").write_text(original + "\n" + r"Text\\% comment \cite{missing}", encoding="utf-8")
        with patch.object(AUDIT, "command", self.command):
            self.assertEqual(AUDIT.audit_paper(self.paper)["cited_entries"], 56)
        (self.paper / "main.tex").write_text(original + "\n" + r"Text\% active \cite{missing}", encoding="utf-8")
        with patch.object(AUDIT, "command", self.command), self.assertRaisesRegex(AUDIT.ReleaseAuditError, "missing"):
            AUDIT.audit_paper(self.paper)

    def test_stale_compiled_bibliography_is_rejected(self) -> None:
        (self.paper / "main.bbl").write_text("\\bibitem{source0} entry\n", encoding="utf-8")
        with patch.object(AUDIT, "command", self.command), self.assertRaisesRegex(AUDIT.ReleaseAuditError, "bibliography differs"):
            AUDIT.audit_paper(self.paper)

    def test_pdf_command_output_is_decoded_as_utf8(self) -> None:
        text = "\u03b1 \u00e9"
        output = AUDIT.command(sys.executable, "-c",
            "import sys; sys.stdout.buffer.write(bytes.fromhex('ceb120c3a9'))")
        self.assertEqual(output, text)


if __name__ == "__main__":
    unittest.main()
