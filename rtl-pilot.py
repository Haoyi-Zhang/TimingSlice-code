#!/usr/bin/env python3
"""Translate fixed public RTL examples and replay two independent acceptance paths.

The dynamic path compares every bounded state/completion sample with a separately
written reference transition function.  The structural path asks a separately
implemented source parser/compiler to validate the exact RTL-to-equation
translation, including source-blob, harness, domain, initialization, completion,
and cut-policy bindings.  Neither path establishes unrestricted Verilog support.
"""
from __future__ import annotations

import argparse
import copy
import csv
import itertools
import json
import math
from pathlib import Path
import resource
import signal
import sys
import time

from src import checker, producer, rtl_frontend, rtl_translation_checker


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        if not rows:
            return
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def parse_domains(text: str) -> dict[str, list[int]]:
    if not text:
        return {}
    result: dict[str, list[int]] = {}
    for field in text.split(";"):
        name, values = field.split("=", 1)
        result[name] = [int(value) for value in values.split(",")]
    return result


def parse_state(text: str) -> dict[str, int]:
    if not text:
        return {}
    return {
        item.split("=", 1)[0]: int(item.split("=", 1)[1])
        for item in text.split(";")
    }


def parse_cuttable(text: str) -> set[str]:
    return {name for name in text.replace(",", ";").split(";") if name}


def reference_step(case: str, state: dict[str, int], inputs: dict[str, int]) -> dict[str, int]:
    if case in ("cmos-counter-3", "intro-counter-2"):
        width = 3 if case == "cmos-counter-3" else 2
        value = state["count"]
        return {
            "count": 0
            if inputs["rst"]
            else ((value + 1) & ((1 << width) - 1) if inputs["en"] else value)
        }
    if case == "smt2-counter":
        value = state["counter"]
        return {"counter": 0 if value == 10 else (value + 1) & 15}
    if case == "verific-counter":
        return {"cnt": 0 if inputs["rst"] else (state["cnt"] + 1) & 15}
    if case == "smtbmc-demo4":
        operand = inputs["in"]
        if inputs["rst"]:
            return {"r1": operand & 0xFFFF, "r2": (-operand) & 0xFFFF}
        next_r1 = (state["r1"] + operand) & 0xFFFF
        delta = (state["r2"] - operand) & 0xFFFF
        next_r2 = (-delta) & 0xFFFF if inputs["inv2"] else delta
        return {"r1": next_r1, "r2": next_r2}
    if case == "asic-up-counter-8":
        value = state["out"]
        return {
            "out": 0
            if inputs["reset"]
            else ((value + 1) & 0xFF if inputs["enable"] else value)
        }
    if case == "asic-up-down-8":
        value = state["out"]
        return {
            "out": 0
            if inputs["reset"]
            else ((value + 1) & 0xFF if inputs["up_down"] else (value - 1) & 0xFF)
        }
    if case == "asic-load-counter-8":
        value = state["out"]
        if inputs["reset"]:
            return {"out": 0}
        if inputs["load"]:
            return {"out": inputs["data"] & 0xFF}
        if inputs["enable"]:
            return {"out": (value + 1) & 0xFF}
        return {"out": value}
    if case == "asic-tutorial-counter-4":
        value = state["count"]
        return {
            "count": 0
            if inputs["reset"]
            else ((value + 1) & 0xF if inputs["enable"] else value)
        }
    if case == "sat-priority-counter-4":
        value = state["counter"]
        return {
            "counter": 0
            if inputs["rst"] or value == 9
            else (value + 1) & 0xF
        }
    raise AssertionError(f"no independent reference semantics for {case}")


def done(case: str, state: dict[str, int]) -> int:
    if case == "cmos-counter-3":
        return int(state["count"] == 3)
    if case == "intro-counter-2":
        return int(state["count"] == 2)
    if case == "smt2-counter":
        return int(state["counter"] == 3)
    if case == "verific-counter":
        return int(state["cnt"] == 3)
    if case == "smtbmc-demo4":
        return int(state["r1"] == 3)
    if case == "asic-up-counter-8":
        return int(state["out"] == 3)
    if case == "asic-up-down-8":
        return int(state["out"] == 2)
    if case == "asic-load-counter-8":
        return int(state["out"] == 7)
    if case == "asic-tutorial-counter-4":
        return int(state["count"] == 3)
    if case == "sat-priority-counter-4":
        return int(state["counter"] == 3)
    raise AssertionError(case)


def all_traces(domains: list[list[int]], steps: int):
    alphabet = list(itertools.product(*domains)) if domains else [()]
    return itertools.product(alphabet, repeat=steps)


class Mismatch(AssertionError):
    def __init__(self, detail, checks: int):
        super().__init__(detail)
        self.checks = checks


def compare_model(case: str, raw: dict) -> tuple[dict, int]:
    """Exhaustively replay the bounded harness against an independent oracle."""
    model = producer.Model(raw)
    register_names = [declaration["name"] for declaration in raw["registers"]]
    input_names = [declaration["name"] for declaration in raw["inputs"]]
    sample_checks = 0
    traces = 0
    domains = [declaration["values"] for declaration in raw["inputs"]]
    default_input = tuple(values[0] for values in domains)
    for trace in all_traces(domains, raw["horizon"]):
        traces += 1
        reference = {declaration["name"]: declaration["init"] for declaration in raw["registers"]}
        equation_state = model.initial
        for step in range(raw["horizon"] + 1):
            sample_checks += 1
            if tuple(reference[name] for name in register_names) != equation_state:
                raise Mismatch((case, "state", step, trace, reference, equation_state), sample_checks)
            input_tuple = trace[step] if step < raw["horizon"] else default_input
            input_map = dict(zip(input_names, input_tuple))
            observed, environment = model.observe(equation_state, input_tuple)
            expected_done = done(case, reference)
            if observed != expected_done:
                raise Mismatch((case, "done", step, trace, observed, expected_done, reference), sample_checks)
            if step < raw["horizon"]:
                reference = reference_step(case, reference, input_map)
                equation_state = model.advance(environment)
    return {
        "case": case,
        "traces": traces,
        "samples": sample_checks,
        "registers": len(raw["registers"]),
        "register_bits": sum(declaration["width"] for declaration in raw["registers"]),
        "inputs": len(raw["inputs"]),
        "input_alphabet": max(1, math.prod(len(declaration["values"]) for declaration in raw["inputs"])),
        "horizon": raw["horizon"],
        "expression_nodes": model.nodes,
        "full_state_and_done_match": True,
    }, sample_checks


def dynamic_negative_controls(raw_by_case: dict[str, dict]) -> list[dict]:
    """Known mistranslations that the independent bounded transition oracle must expose."""
    rows: list[dict] = []
    for case, mutation in [
        ("intro-counter-2", "drop-enable-hold"),
        ("verific-counter", "invert-reset-priority"),
        ("smtbmc-demo4", "use-old-r1-for-r2"),
    ]:
        bad = copy.deepcopy(raw_by_case[case])
        if case == "intro-counter-2":
            declaration = bad["registers"][0]
            declaration["next"] = [
                "mux", ["var", "rst"], ["const", 2, 0],
                ["add", ["var", "count"], ["const", 2, 1]],
            ]
        elif case == "verific-counter":
            declaration = bad["registers"][0]
            declaration["next"] = [
                "mux", ["var", "rst"],
                ["add", ["var", "cnt"], ["const", 4, 1]], ["const", 4, 0],
            ]
        else:
            for declaration in bad["registers"]:
                if declaration["name"] == "r2":
                    def replace(node):
                        if node == ["var", "r2"]:
                            return ["var", "r1"]
                        return [replace(value) if isinstance(value, list) else value for value in node]
                    declaration["next"] = replace(declaration["next"])
        caught = False
        checks = 0
        try:
            compare_model(case, bad)
        except Mismatch as error:
            caught = True
            checks = error.checks
        if not caught:
            raise AssertionError(f"dynamic negative control escaped: {case}/{mutation}")
        rows.append({
            "case": case,
            "mutation": mutation,
            "oracle_detected": caught,
            "paired_samples_to_detection": checks,
        })
    return rows


def translation_negative_controls(
    sources: dict[str, tuple[str, bytes, dict[str, str]]],
    raw_by_case: dict[str, dict],
    cut_by_case: dict[str, set[str]],
) -> list[dict]:
    """Mutate each binding class and require the independent validator to reject."""
    cases: list[tuple[str, str, str, bytes, dict[str, str], dict, set[str]]] = []

    def add(base: str, mutation: str, *, source_text: str | None = None,
            source_bytes: bytes | None = None, manifest: dict[str, str] | None = None,
            raw: dict | None = None, cuttable: set[str] | None = None) -> None:
        text, payload, row = sources[base]
        cases.append((
            base, mutation,
            text if source_text is None else source_text,
            payload if source_bytes is None else source_bytes,
            copy.deepcopy(row if manifest is None else manifest),
            copy.deepcopy(raw_by_case[base] if raw is None else raw),
            set(cut_by_case[base] if cuttable is None else cuttable),
        ))

    base = "cmos-counter-3"
    text, payload, row = sources[base]
    changed_manifest = copy.deepcopy(row)
    changed_manifest["blob_sha"] = "0" * 40
    add(base, "wrong-source-blob-binding", manifest=changed_manifest)
    add(base, "changed-source-bytes", source_bytes=payload + b"\n")

    bad = copy.deepcopy(raw_by_case[base])
    bad["horizon"] += 1
    add(base, "wrong-horizon", raw=bad)

    bad = copy.deepcopy(raw_by_case[base])
    bad["inputs"][0]["values"] = [0]
    add(base, "wrong-input-domain", raw=bad)

    bad = copy.deepcopy(raw_by_case[base])
    bad["registers"][0]["init"] = 1
    add(base, "wrong-initial-state", raw=bad)

    bad = copy.deepcopy(raw_by_case[base])
    bad["registers"][0]["cut"] = False
    add(base, "wrong-cut-policy", raw=bad)

    bad = copy.deepcopy(raw_by_case[base])
    bad["done"] = ["const", 1, 0]
    add(base, "wrong-completion-equation", raw=bad)

    sat = "sat-priority-counter-4"
    bad = copy.deepcopy(raw_by_case[sat])
    bad["registers"][0]["next"] = [
        "mux", ["var", "rst"], ["const", 4, 0],
        ["add", ["var", "counter"], ["const", 4, 1]],
    ]
    add(sat, "drop-case-reset-at-nine", raw=bad)

    results: list[dict] = []
    for case, mutation, source_text, source_bytes, manifest, raw, cuttable in cases:
        rejected = False
        reason = None
        try:
            rtl_translation_checker.validate_translation(
                source_text, source_bytes, manifest, raw, cuttable
            )
        except rtl_translation_checker.TranslationValidationError as error:
            rejected = True
            reason = str(error)
        if not rejected:
            raise AssertionError(f"translation negative control escaped: {case}/{mutation}")
        results.append({
            "case": case,
            "mutation": mutation,
            "independent_validator_rejected": rejected,
            "reason": reason,
        })
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--mode", choices=("generate", "replay"), default="generate",
        help="generate fresh bundles or replay the retained bundles without repeating minimization",
    )
    parser.add_argument(
        "--bundle-dir", type=Path,
        help="retained bundle directory for --mode replay (default: results/rtl-pilot/bundles)",
    )
    args = parser.parse_args()
    if args.out.exists() and any(args.out.iterdir()):
        parser.error("output directory is nonempty")
    args.out.mkdir(parents=True, exist_ok=True)

    resource.setrlimit(resource.RLIMIT_AS, (1024 ** 3, 1024 ** 3))
    resource.setrlimit(resource.RLIMIT_CPU, (110, 115))
    signal.signal(
        signal.SIGALRM,
        lambda *_: (_ for _ in ()).throw(TimeoutError("118-second wall limit")),
    )
    signal.alarm(118)
    started_wall = time.perf_counter()
    started_cpu = time.process_time()
    exit_code = 0
    failure = None
    try:
        root = Path(__file__).resolve().parent
        public = root / "public_rtl" / "yosys"
        bundle_directory = args.bundle_dir or (root / "results" / "rtl-pilot" / "bundles")
        if args.mode == "replay" and not bundle_directory.is_dir():
            raise FileNotFoundError(f"retained bundle directory missing: {bundle_directory}")
        with (public / "manifest.csv").open(newline="") as manifest_file:
            manifest = list(csv.DictReader(manifest_file))

        equivalence_rows: list[dict] = []
        validation_rows: list[dict] = []
        slice_rows: list[dict] = []
        raw_by_case: dict[str, dict] = {}
        cut_by_case: dict[str, set[str]] = {}
        sources: dict[str, tuple[str, bytes, dict[str, str]]] = {}
        sample_checks = 0
        structural_units = 0
        producer_units = 0
        retained_producer_units = 0
        checker_units = 0

        for item in manifest:
            source_path = public / item["path"]
            source_bytes = source_path.read_bytes()
            source_text = source_bytes.decode("utf-8")
            cuttable = parse_cuttable(item.get("cuttable", ""))
            raw, _module = rtl_frontend.translate(
                source_text,
                module_name=item["module"],
                model_id=item["case_id"],
                clock=item["clock"],
                done_expression=item["done_expression"],
                horizon=int(item["horizon"]),
                domains=parse_domains(item["input_domains"]),
                initial_state=parse_state(item["initial_state"]),
                cuttable=cuttable,
            )
            producer.Model(raw)  # equation-IR contract and type check
            validation = rtl_translation_checker.validate_translation(
                source_text, source_bytes, item, raw, cuttable
            )
            validation_rows.append(validation)
            structural_units += int(validation["structural_comparison_units"])
            write_json(args.out / "translation-validation" / f"{item['case_id']}.json", validation)

            case = item["case_id"]
            raw_by_case[case] = raw
            cut_by_case[case] = cuttable
            sources[case] = (source_text, source_bytes, item)
            write_json(args.out / "translated" / f"{case}.json", raw)

            equivalence, checks = compare_model(case, raw)
            equivalence.update({"source_path": item["path"], "source_blob": item["blob_sha"]})
            equivalence_rows.append(equivalence)
            sample_checks += checks

            if cuttable:
                model = producer.Model(raw)
                if args.mode == "generate":
                    bundle = producer.bundle(model, "first-hit", limit=20_000)
                    write_json(args.out / "bundles" / f"{case}-first-hit.json", bundle)
                    producer_executed = True
                else:
                    bundle_path = bundle_directory / f"{case}-first-hit.json"
                    bundle = json.loads(bundle_path.read_text())
                    producer_executed = False
                if bundle["status"] != "inclusion-minimal":
                    raise AssertionError(f"bundle not inclusion-minimal for {case}: {bundle['status']}")
                verified = checker.verify_bundle(raw, bundle, limit=20_000)
                if not verified.get("accepted"):
                    raise AssertionError(f"independent checker rejected {case}: {verified}")
                producer_work = bundle["work"]["observations"] + bundle["work"]["successors"]
                checker_work = verified["work"]["observations"] + verified["work"]["successors"]
                retained_producer_units += producer_work
                if producer_executed:
                    producer_units += producer_work
                checker_units += checker_work
                slice_rows.append({
                    "case": case,
                    "candidates": len(model.candidates),
                    "retained": len(bundle["preservation"]["retained"]),
                    "retained_ids": ";".join(bundle["preservation"]["retained"]),
                    "producer_obligations": producer_work,
                    "producer_executed_this_run": producer_executed,
                    "checker_obligations": checker_work,
                    "status": bundle["status"],
                })

        dynamic_controls = dynamic_negative_controls(raw_by_case) if args.mode == "generate" else []
        translation_controls = (
            translation_negative_controls(sources, raw_by_case, cut_by_case)
            if args.mode == "generate" else []
        )
        write_csv(args.out / "rtl_equivalence.csv", equivalence_rows)
        write_csv(args.out / "translation_validation.csv", validation_rows)
        write_csv(args.out / "rtl_slice_bundles.csv", slice_rows)
        write_csv(args.out / "rtl_negative_controls.csv", dynamic_controls)
        write_csv(args.out / "translation_validation_mutations.csv", translation_controls)

        dynamic_negative_checks = sum(
            int(row["paired_samples_to_detection"]) for row in dynamic_controls
        )
        validator_mutation_checks = len(translation_controls)
        # Campaign enumeration accounting counts one accepted translation obligation
        # per source, not each internal AST-node comparison.  The latter remains an
        # independently reported diagnostic and is not double-counted as semantic work.
        translation_validation_obligations = len(validation_rows)
        total_units = (
            sample_checks
            + dynamic_negative_checks
            + translation_validation_obligations
            + validator_mutation_checks
            + producer_units
            + checker_units
        )
        summary = {
            "status": "PASS",
            "mode": args.mode,
            "public_rtl_modules": len(equivalence_rows),
            "source_blobs_independently_verified": len(validation_rows),
            "full_state_and_done_sample_checks": sample_checks,
            "translation_validation_obligations": translation_validation_obligations,
            "structural_translation_comparison_units": structural_units,
            "dynamic_negative_control_sample_checks": dynamic_negative_checks,
            "translation_validator_mutation_checks": validator_mutation_checks,
            "producer_semantic_obligations_executed": producer_units,
            "retained_producer_semantic_obligations": retained_producer_units,
            "checker_semantic_obligations": checker_units,
            "total_semantic_units": total_units,
            "dynamic_translation_mutations_detected": sum(
                bool(row["oracle_detected"]) for row in dynamic_controls
            ),
            "translation_binding_mutations_rejected": sum(
                bool(row["independent_validator_rejected"]) for row in translation_controls
            ),
            "first_completion_bundles_checked": len(slice_rows),
            "scope": "fixed Yosys sources in a documented restricted single-clock two-state subset; finite transaction harnesses",
            "not_established": [
                "unrestricted Verilog/SystemVerilog parsing",
                "mechanized correctness of either source parser",
                "accelerator workload coverage",
                "physical timing or simulation speedup",
            ],
        }
        write_json(args.out / "summary.json", summary)
        print(json.dumps(summary, indent=2, sort_keys=True))
    except Exception as error:  # preserve an exact failure receipt
        exit_code = 1
        failure = repr(error)
        print(failure, file=sys.stderr)
    finally:
        signal.alarm(0)
        write_json(args.out / "run.json", {
            "command": (
                f"python3 rtl-pilot.py --out {args.out} --mode {args.mode}"
                + (f" --bundle-dir {args.bundle_dir}" if args.bundle_dir else "")
            ),
            "exit_code": exit_code,
            "wall_seconds": time.perf_counter() - started_wall,
            "cpu_seconds": time.process_time() - started_cpu,
            "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "worker_processes": 1,
            "failure": failure,
        })
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
