#!/usr/bin/env python3
"""Audit artifact closure and, when supplied, the complete paper/project release.

This verifier is intentionally static: it consumes retained receipts and build
products and does not repeat minimization, mutation campaigns, or frontier replay.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any


class ReleaseAuditError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ReleaseAuditError(message)


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ReleaseAuditError(f"cannot read {path}: {error}") from error


def csv_rows(path: Path) -> list[dict[str, str]]:
    try:
        with path.open(newline="") as handle:
            return list(csv.DictReader(handle))
    except OSError as error:
        raise ReleaseAuditError(f"cannot read {path}: {error}") from error


def command(*args: str, cwd: Path | None = None) -> str:
    completed = subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=False)
    require(completed.returncode == 0,
            f"command failed ({completed.returncode}): {' '.join(args)}\n{completed.stderr}")
    return completed.stdout


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def forbidden_payload_paths(root: Path) -> list[str]:
    """Check delivered content, not the outer checkout's Git metadata."""
    forbidden = []
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if relative.parts[0] == '.git':
            continue
        if path.name in {"__pycache__", ".git", ".pytest_cache", ".coverage"}:
            forbidden.append(relative.as_posix())
        elif path.is_file() and path.suffix in {".pyc", ".zip"}:
            forbidden.append(relative.as_posix())
    return forbidden


def audit_artifact(root: Path) -> dict[str, Any]:
    required_files = {
        "README.md", "LICENSE", "ir-contract.md", "rtl-subset.md",
        "pilot-protocol.md", "reproduce.py", "rtl-pilot.py", "run-tests.py",
        "verify-retained.py", "verify-release.py", "verify-paper-data.py",
        "audit-bibliography.py",
        "claim_evidence_ledger.csv", "external_resources.csv",
        "literature-calibration.csv", "bibliography-audit.csv",
    }
    required_dirs = {"src", "tests", "cases", "proofs", "results", "public_rtl"}
    present = {path.name for path in root.iterdir()}
    require(required_files <= present, f"artifact required files missing: {sorted(required_files - present)}")
    require(required_dirs <= present, f"artifact required directories missing: {sorted(required_dirs - present)}")

    forbidden = forbidden_payload_paths(root)
    require(not forbidden, f"forbidden runtime/archive files: {forbidden}")

    # Check syntax without writing bytecode or deleting any checkout paths.
    # compileall writes .pyc even under -B, so it is not a read-only audit.
    sources = sorted(root.glob("*.py"))
    sources += sorted((root / "src").rglob("*.py"))
    sources += sorted((root / "tests").rglob("*.py"))
    for source in sources:
        try:
            compile(source.read_bytes(), str(source), "exec")
        except (SyntaxError, ValueError) as error:
            raise ReleaseAuditError(f"Python compile failure in {source}: {error}") from error

    retained = read_json(root / "results" / "final-retained-audit.json")
    require(retained.get("status") == "PASS", "retained static audit is not PASS")
    regression = read_json(root / "results" / "software-regression.json")
    require(regression.get("status") == "PASS", "software regression suite is not PASS")
    paper_data = read_json(root / "results" / "paper-data-audit.json")
    require(paper_data.get("status") == "PASS", "paper-data reconciliation is not PASS")
    require(regression.get("tests_run", 0) >= 15, "software regression suite is too small")
    require(regression.get("failures") == 0 and regression.get("errors") == 0,
            "software regression receipt contains failures")
    require(regression.get("semantic_units_this_run") == 102,
            "retained software-regression accounting is not corrected to 102")
    require(regression.get("suite_definition_after_repair_tests") == 21,
            "repaired suite definition is not 21 tests")

    pre_fix = read_json(root / "results" / "translation-static-risk-pre-fix.json")
    require(pre_fix.get("results", {}).get(
        "source_text_source_bytes_joint_substitution", {}).get("outcome") == "ACCEPT",
        "pre-fix source-text risk receipt is missing or rewritten")
    require(pre_fix.get("results", {}).get(
        "external_cuttable_joint_substitution", {}).get("outcome") == "ACCEPT",
        "pre-fix cuttable risk receipt is missing or rewritten")
    targeted = read_json(root / "results" / "translation-static-risk-postfix.json")
    require(targeted.get("status") == "PASS" and targeted.get("tests_run") == 5,
            "post-fix targeted regression is not a five-method PASS")
    require(targeted.get("semantic_units_this_run") == 21,
            "post-fix targeted regression is not 21 semantic units")
    targeted_counts = targeted.get("counts", {})
    expected_targeted = {
        "accepted_translation_validations": 10,
        "translation_binding_mutation_checks": 8,
        "source_byte_substitution_checks": 1,
        "detached_source_text_joint_substitution_checks": 1,
        "external_cuttable_joint_substitution_checks": 1,
    }
    for key, value in expected_targeted.items():
        require(targeted_counts.get(key) == value,
                f"post-fix targeted count differs: {key}")

    accounting = read_json(root / "results" / "campaign-accounting.json")
    cumulative = accounting.get("cumulative_semantic_work")
    ceiling = accounting.get("campaign_semantic_work_cap")
    remaining = accounting.get("remaining_semantic_work")
    overrun = accounting.get("semantic_work_overrun")
    require(type(cumulative) is int and type(ceiling) is int and
            type(remaining) is int and type(overrun) is int,
            "campaign accounting fields are not integers")
    require(ceiling == 150000 and cumulative == ceiling - remaining + overrun,
            "campaign accounting does not close with remaining/overrun")
    require(remaining == 0 and overrun == 22 and cumulative == 150022,
            "final campaign totals are not 150022 with a 22-unit overrun")
    require(accounting.get("historical_campaign_after_accounting_correction") == 149999,
            "corrected historical freeze is not 149999")
    require(regression.get("semantic_units_this_run") ==
            accounting.get("software_regression_semantic_work"),
            "software regression work is not reconciled with campaign accounting")
    require(accounting.get("translation_static_risk_pre_fix_semantic_work") == 2,
            "pre-fix risk-probe work is not reconciled")
    require(accounting.get("translation_static_risk_post_fix_semantic_work") ==
            targeted.get("semantic_units_this_run"),
            "post-fix targeted work is not reconciled")

    cases = sorted((root / "cases").glob("*.json"))
    require(len(cases) == 109, "fixture count is not 109")
    ledger = csv_rows(root / "claim_evidence_ledger.csv")
    require(len(ledger) >= 20, "claim ledger is unexpectedly small")
    for index, row in enumerate(ledger, 2):
        for field in ("claim_id", "claim", "raw_evidence", "maturity", "fresh_recheck_and_boundary"):
            require(row.get(field, "").strip(), f"claim ledger row {index} lacks {field}")

    resources = csv_rows(root / "external_resources.csv")
    require(resources, "external resource inventory is empty")
    for index, row in enumerate(resources, 2):
        for field in ("name", "url", "license", "access_date", "status"):
            require(row.get(field, "").strip(), f"external resource row {index} lacks {field}")

    manifest = csv_rows(root / "public_rtl" / "yosys" / "manifest.csv")
    require(len(manifest) == 10, "public RTL manifest does not have ten rows")
    for row in manifest:
        source = root / "public_rtl" / "yosys" / row["path"]
        require(source.is_file(), f"public RTL source missing: {row['path']}")
        require(git_blob_sha(source.read_bytes()) == row["blob_sha"],
                f"public RTL blob mismatch: {row['case_id']}")
    require("ISC License" in (root / "public_rtl" / "yosys" / "LICENSE-ISC.txt").read_text(),
            "Yosys ISC notice missing")

    calibration = csv_rows(root / "literature-calibration.csv")
    classes: dict[str, int] = {}
    for row in calibration:
        classes[row["class"]] = classes.get(row["class"], 0) + 1
        require(row["reading_scope"].strip(), "literature calibration lacks reading scope")
        require(row["delta_for_this_project"].strip(), "literature calibration lacks project delta")
    require(len(calibration) >= 22, "literature calibration has fewer than 22 full-paper rows")

    return {
        "status": "PASS",
        "python_sources_compile": True,
        "software_regression_tests": regression["tests_run"],
        "software_regression_semantic_units": regression["semantic_units_this_run"],
        "targeted_translation_repair_test_methods": targeted["tests_run"],
        "targeted_translation_repair_semantic_units": targeted["semantic_units_this_run"],
        "paper_data_reconciliation": True,
        "retained_static_audit": True,
        "case_files": len(cases),
        "claim_ledger_rows": len(ledger),
        "external_resource_rows": len(resources),
        "public_rtl_sources": len(manifest),
        "literature_calibration_rows": len(calibration),
        "literature_calibration_classes": classes,
        "campaign_cumulative_semantic_work": cumulative,
        "campaign_remaining_semantic_work": remaining,
        "campaign_semantic_work_overrun": overrun,
    }


def bib_entries(text: str) -> tuple[list[str], dict[str, str]]:
    starts = list(re.finditer(r"(?m)^@(\w+)\s*\{\s*([^,\s]+)\s*,", text))
    keys: list[str] = []
    bodies: dict[str, str] = {}
    for index, match in enumerate(starts):
        key = match.group(2)
        end = starts[index + 1].start() if index + 1 < len(starts) else len(text)
        keys.append(key)
        bodies[key] = text[match.start():end]
    return keys, bodies


def audit_paper(paper: Path) -> dict[str, Any]:
    tex_path = paper / "main.tex"
    bib_path = paper / "references.bib"
    pdf_path = paper / "paper.pdf"
    require(tex_path.is_file() and bib_path.is_file() and pdf_path.is_file(),
            "paper source, bibliography, or PDF missing")
    tex = tex_path.read_text()
    bib = bib_path.read_text()

    keys, bodies = bib_entries(bib)
    require(len(keys) == len(set(keys)), "duplicate BibTeX keys")
    require(len(keys) >= 55, "bibliography has fewer than 55 entries")
    cited: set[str] = set()
    for match in re.finditer(r"\\cite(?:\[[^\]]*\])?\{([^}]+)\}", tex):
        cited |= {item.strip() for item in match.group(1).split(",") if item.strip()}
    missing = cited - set(keys)
    uncited = set(keys) - cited
    require(not missing, f"citation keys missing from bibliography: {sorted(missing)}")
    require(not uncited, f"uncited bibliography entries: {sorted(uncited)}")
    for key, body in bodies.items():
        for field in ("author", "title", "year"):
            require(re.search(rf"(?mi)^\s*{field}\s*=", body) is not None,
                    f"bibliography entry {key} lacks {field}")
        require(any(re.search(rf"(?mi)^\s*{field}\s*=", body) for field in
                    ("journal", "booktitle", "publisher", "howpublished")),
                f"bibliography entry {key} lacks a publication venue/type")
    recent = [key for key, body in bodies.items()
              if re.search(r"(?mi)^\s*year\s*=\s*\{?(202[5-9])", body)]
    for key in recent:
        require(re.search(r"(?mi)^\s*(doi|url|howpublished)\s*=", bodies[key]) is not None,
                f"recent bibliography entry {key} lacks a stable locator")

    sections = re.findall(r"(?m)^\\section\{", tex)
    require(7 <= len(sections) <= 9, f"main section count is {len(sections)}, expected 7--9")
    abstract_match = re.search(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", tex, re.S)
    require(abstract_match is not None, "abstract missing")
    abstract_plain = re.sub(r"\\[A-Za-z]+(?:\{[^{}]*\})?", " ", abstract_match.group(1))
    abstract_words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'\-]*", abstract_plain)
    require(100 <= len(abstract_words) <= 250,
            f"abstract word count {len(abstract_words)} is outside 100--250")
    keyword_match = re.search(r"\\begin\{IEEEkeywords\}(.*?)\\end\{IEEEkeywords\}", tex, re.S)
    require(keyword_match is not None, "keywords missing")
    keywords = [item.strip().rstrip(".") for item in keyword_match.group(1).replace("\n", " ").split(",")]
    require(4 <= len(keywords) <= 8, f"keyword count is {len(keywords)}, expected 4--8")

    forbidden_layout = [r"\\vspace\s*\{\s*-", r"\\fontsize\s*\{", r"\\linespread\s*\{"]
    for pattern in forbidden_layout:
        require(re.search(pattern, tex) is None, f"forbidden layout manipulation matches {pattern}")

    info = command("pdfinfo", str(pdf_path))
    page_match = re.search(r"(?m)^Pages:\s+(\d+)", info)
    size_match = re.search(r"(?m)^Page size:\s+([0-9.]+) x ([0-9.]+) pts", info)
    require(page_match and int(page_match.group(1)) == 12, "paper PDF is not exactly 12 pages")
    require(size_match, "paper page size unavailable")
    width, height = float(size_match.group(1)), float(size_match.group(2))
    require(abs(width - 612) < 1 and abs(height - 792) < 1, "paper is not US Letter")

    fonts = command("pdffonts", str(pdf_path)).splitlines()[2:]
    require(fonts, "paper PDF reports no fonts")
    for line in fonts:
        parts = line.split()
        require("yes" in parts, f"font row does not report embedding: {line}")
        # pdffonts columns include emb/sub/uni; the first yes after type is emb.
        require(parts[parts.index("yes")] == "yes", f"unembedded font: {line}")

    extracted = command("pdftotext", str(pdf_path), "-")
    require("[?]" not in extracted and "Citation" not in extracted,
            "paper text extraction contains unresolved placeholder text")
    require("Proof-Carrying Bounded Dependency Slices" in extracted,
            "paper title is not recoverable from PDF")
    compact_pdf_text = re.sub(r"\s+", "", extracted).upper()
    require("REFERENCES" in compact_pdf_text, "references heading missing from PDF")

    log_path = paper / "main.log"
    require(log_path.is_file(), "final LaTeX build log missing")
    log = log_path.read_text(errors="replace")
    for defect in ("Overfull \\hbox", "Overfull \\vbox", "undefined references",
                   "Citation `", "There were undefined references"):
        require(defect not in log, f"LaTeX log defect: {defect}")

    figures = sorted((paper / "figures").glob("*.tex"))
    tables = sorted(paper.glob("*-table.tex"))
    require(len(figures) == 3, "expected exactly three LaTeX-native figure sources")
    require(len(tables) == 3, "expected three external table sources")

    return {
        "status": "PASS",
        "pages": 12,
        "page_size": "US Letter",
        "fonts_embedded": True,
        "main_sections": len(sections),
        "abstract_words": len(abstract_words),
        "keywords": len(keywords),
        "bibliography_entries": len(keys),
        "cited_entries": len(cited),
        "missing_citations": 0,
        "uncited_entries": 0,
        "recent_entries_with_stable_locator": len(recent),
        "latex_native_figures": len(figures),
        "external_table_sources": len(tables),
    }


def audit_project(project: Path, artifact: Path) -> dict[str, Any]:
    expected = {"README.md", "artifact", "paper"}
    actual = {path.name for path in project.iterdir()}
    require(actual == expected, f"project root entries differ: {sorted(actual)}")
    require(artifact.resolve() == (project / "artifact").resolve(),
            "artifact argument is not the project's artifact directory")
    require((project / "paper" / "provenance" / "research-plan.md").stat().st_size > 0, "research plan is empty")
    require((project / "paper" / "provenance" / "CURRENT-STATE.md").stat().st_size > 0, "current state is empty")
    text_suffixes = {".py", ".md", ".csv", ".json", ".txt", ".tex", ".bib", ".log", ".bbl"}
    private_markers = ("/" + "mnt/data", "/" + "home/oai", "sandbox" + ":", "user-" + "BTr")
    leaks: list[str] = []
    for path in project.rglob("*"):
        if path.is_file() and path.suffix.lower() in text_suffixes:
            content = path.read_text(errors="replace")
            if any(marker in content for marker in private_markers):
                leaks.append(path.relative_to(project).as_posix())
    require(not leaks, f"private runtime path markers remain: {leaks}")
    return {"status": "PASS", "root_entries": sorted(actual), "private_path_markers": 0}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--project-root", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        artifact = args.artifact.resolve()
        report: dict[str, Any] = {"status": "PASS", "artifact": audit_artifact(artifact)}
        if args.project_root is not None:
            project = args.project_root.resolve()
            report["project"] = audit_project(project, artifact)
            report["paper"] = audit_paper(project / "paper")
    except (ReleaseAuditError, OSError, ValueError) as error:
        report = {"status": "FAIL", "reason": str(error)}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
