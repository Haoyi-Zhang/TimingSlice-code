#!/usr/bin/env python3
"""Statically reconcile manuscript figures/tables with retained raw evidence."""
from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any


class PaperDataError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PaperDataError(message)


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise PaperDataError(f"cannot read {path}: {error}") from error


def read_csv(path: Path) -> list[dict[str, str]]:
    try:
        with path.open(newline="") as handle:
            return list(csv.DictReader(handle))
    except (OSError, csv.Error) as error:
        raise PaperDataError(f"cannot read {path}: {error}") from error


def frontier_lengths(bundle: dict[str, Any]) -> list[int]:
    preservation = bundle.get("preservation", bundle)
    rows = preservation.get("frontiers")
    require(isinstance(rows, list), "bundle has no frontier list")
    return [len(row) for row in rows]


def normalize_tex(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\\,", ",")).strip()


def audit(root: Path, project: Path) -> dict[str, Any]:
    paper = project / "paper"
    results = root / "results" / "clean-reproduction"

    # Figure 3: every plotted point must come directly from retained bundles.
    plotted = read_csv(paper / "figures" / "frontiers.csv")
    first = frontier_lengths(read_json(results / "bundles" / "post-completion-first-hit.json"))
    wave = frontier_lengths(read_json(results / "bundles" / "post-completion-waveform.json"))
    unsliced = frontier_lengths(read_json(results / "baselines" / "post-completion-unsliced-first-hit.json"))
    expected_plot = [
        {
            "cycle": str(index),
            "first_hit": str(first[index]),
            "waveform": str(wave[index]),
            "unsliced_first_hit": str(unsliced[index]),
        }
        for index in range(len(first))
    ]
    require(plotted == expected_plot, "frontiers.csv differs from retained bundle frontiers")

    baselines = {row["configuration"]: row for row in read_csv(results / "post_completion_baselines.csv")}
    require(int(baselines["sliced-first-hit"]["frontier_entries"]) == sum(first),
            "sliced first-hit frontier total mismatch")
    require(int(baselines["sliced-waveform"]["frontier_entries"]) == sum(wave),
            "waveform frontier total mismatch")
    require(int(baselines["unsliced-first-hit"]["frontier_entries"]) == sum(unsliced),
            "unsliced first-hit frontier total mismatch")

    # Table III: values are a two-observer projection of control_results.csv.
    controls = read_csv(results / "control_results.csv")
    by_case: dict[str, dict[str, dict[str, str]]] = {}
    for row in controls:
        by_case.setdefault(row["case"], {})[row["observation"]] = row
    labels = [
        ("joint-omission", "Joint omission"),
        ("zero-cancellation", "Zero cancellation"),
        ("post-completion", "Post-completion"),
        ("enable-counter", "Enable counter"),
        ("reset-counter", "Reset counter"),
        ("old-value-pipeline", "Old-value pipeline"),
        ("wrap-counter", "Wrap counter"),
        ("never-complete", "Never completes"),
        ("initial-completion", "Initially complete"),
        ("wire-width", "Wire width"),
        ("concat-slice", "Concat and slice"),
        ("shared-wire", "Shared wire"),
        ("minimum-gap", "Cardinality gap"),
    ]
    table_text = normalize_tex((paper / "control-table.tex").read_text())
    checked_control_rows = 0
    for case, label in labels:
        require(case in by_case and set(by_case[case]) == {"first-hit", "waveform"},
                f"control result pair missing for {case}")
        f = by_case[case]["first-hit"]
        w = by_case[case]["waveform"]
        expected = normalize_tex(
            f"{label} & {f['candidates']} & {f['retained']} & {w['retained']} & "
            f"{f['frontier_entries']} & {w['frontier_entries']} & "
            f"{f['preservation_obligations']} & {w['preservation_obligations']} \\\\"
        )
        require(expected in table_text, f"control-table row differs from raw evidence: {case}")
        checked_control_rows += 1

    # Table II: ten public cases, per-case trace/sample counts, totals, and bundle marks.
    rtl_rows = {row["case"]: row for row in read_csv(root / "results" / "rtl-pilot" / "rtl_equivalence.csv")}
    accepted = {row["case"] for row in read_csv(root / "results" / "rtl-pilot" / "rtl_slice_bundles.csv")}
    display = {
        "cmos-counter-3": "CMOS counter",
        "intro-counter-2": "Intro counter",
        "smt2-counter": "SMT2 self-reset",
        "verific-counter": "Verific counter",
        "smtbmc-demo4": "SMTBMC pair",
        "asic-up-counter-8": "ASIC up counter",
        "asic-up-down-8": "ASIC up/down",
        "asic-load-counter-8": "ASIC load counter",
        "asic-tutorial-counter-4": "Tutorial counter",
        "sat-priority-counter-4": "SAT priority case",
    }
    require(set(rtl_rows) == set(display), "RTL table source set differs from the fixed ten cases")
    rtl_tex = normalize_tex((paper / "rtl-table.tex").read_text())
    for case, label in display.items():
        row = rtl_rows[case]
        shown = label + ("$^*$" if case in accepted else "")
        expected_fragment = normalize_tex(
            f"{shown} & {row['horizon']} & {int(row['traces']):,} & {int(row['samples']):,}"
        )
        require(expected_fragment in rtl_tex, f"RTL table values differ for {case}")
    traces = sum(int(row["traces"]) for row in rtl_rows.values())
    samples = sum(int(row["samples"]) for row in rtl_rows.values())
    require(traces == 1377 and samples == 4965, "RTL totals differ from retained campaign")
    require("Total: 10 modules, 1,377 traces, 4,965 samples" in rtl_tex,
            "RTL table total line differs from raw evidence")

    # Mutation and budget statements: exact retained outcomes must remain visible.
    mutations = read_csv(results / "mutation_results.csv")
    rejected = sum(row["expected_accepted"] == "False" and row["accepted"] == "False"
                   and not row["reason"].startswith("UNKNOWN") for row in mutations)
    accepted_supersets = sum(row["mutation"] == "sound-frontier-superset" and row["accepted"] == "True"
                             for row in mutations)
    unknown = sum(row["reason"].startswith("UNKNOWN") for row in mutations)
    require((rejected, accepted_supersets, unknown) == (16, 1, 2),
            "retained certificate-control counts changed")
    main_tex = normalize_tex((paper / "main.tex").read_text())
    require("Sixteen invalid evidence mutations are rejected" in main_tex,
            "paper no longer states the exact rejected-mutation count")
    require("two zero-budget controls return UNKNOWN" in main_tex,
            "paper no longer states the exact UNKNOWN controls")
    require("149,999" in main_tex and "150,022" in main_tex and
            "22 above" in main_tex,
            "paper corrected campaign accounting text is missing")

    bibliography = read_json(root / "results" / "bibliography-audit.json")
    require(bibliography.get("status") == "PASS" and bibliography.get("entries") == 56,
            "bibliography audit is not closed at 56 entries")

    return {
        "status": "PASS",
        "scientific_search_repeated": False,
        "figure_3_points_checked": len(expected_plot) * 3,
        "control_table_rows_checked": checked_control_rows,
        "public_rtl_rows_checked": len(rtl_rows),
        "public_rtl_totals": {"traces": traces, "samples": samples},
        "certificate_controls": {
            "invalid_rejected": rejected,
            "sound_superset_accepted": accepted_supersets,
            "unknown_budget_controls": unknown,
        },
        "bibliography_entries_reconciled": 56,
        "campaign_accounting_text_reconciled": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = audit(args.artifact.resolve(), args.project_root.resolve())
    except (PaperDataError, OSError, csv.Error, ValueError) as error:
        report = {"status": "FAIL", "reason": str(error)}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
