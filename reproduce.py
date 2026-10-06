#!/usr/bin/env python3
"""Run the fixed bounded pilot and materialize its evidence, offline.

All cases are synthetic equation systems. Exit 0 means the fixed pilot passed;
it does not establish a general validated Verilog frontend.
"""
from __future__ import annotations

import argparse
import ast
import copy
import csv
import itertools
import json
import signal
import sys
import time
from pathlib import Path

from src import cases, checker, producer
from tests import oracles


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, sort_keys=True, indent=2) + "\n")


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows: raise ValueError("empty evidence table")
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def add_work(total: dict, kind: str, work: dict) -> None:
    total[kind] += work["observations"] + work["successors"]


def semantic_tests(models: list[dict]) -> int:
    total = 0
    for raw in models:
        p = producer.Model(raw)
        q = checker.Semantics(raw)
        free = p.cuts(set(), True) + p.cuts(set(), False)
        for state in itertools.product(*[range(1 << d["width"]) for d in raw["registers"]]):
            for u in p.inputs():
                # Include no-cut and mixed retained/cut contexts. Testing only
                # all-cut valuations would never exercise candidate equations.
                choices = [[None] + list(range(1 << width)) for _, width in free]
                for vals in itertools.product(*choices):
                    cut = {name: value for (name, _), value in zip(free, vals) if value is not None}
                    expected = oracles.hand_step(raw["id"], state, u, cut)
                    dp, ep = p.observe(state, u, cut)
                    dq, eq = q.frame(state, u, cut)
                    assert (dp, p.advance(ep, cut)) == expected, (raw["id"], "producer semantics")
                    assert (dq, q.next_state(eq, cut)) == expected, (raw["id"], "checker semantics")
                    total += 1
    # Snapshot and independently imported checker properties.
    raw = copy.deepcopy(models[2])
    m = producer.Model(raw)
    independent = checker.Semantics(raw)
    raw["registers"][0]["init"] = 3
    assert m.raw["registers"][0]["init"] == 0
    assert independent.data["registers"][0]["init"] == 0
    tree = ast.parse((Path(__file__).parent / "src" / "checker.py").read_text())
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import): imported += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom): imported.append(node.module or "")
    assert not any(x.startswith(("src", "tests")) or "producer" in x for x in imported)
    try:
        checker.strict_pairs([("x", 0), ("x", 1)])
        raise AssertionError("duplicate JSON key accepted")
    except checker.Rejected:
        pass
    return total



def retained_equation_regression(models: list[dict]) -> int:
    """An all-cut-only test would mask this old-state wiring error."""
    original = next(m for m in models if m["id"] == "old-value-pipeline")
    broken = copy.deepcopy(original)
    broken["registers"][1]["next"] = ["var", "go"]
    expected = oracles.hand_step(original["id"], (0, 0), (1,), {})
    p, q = producer.Model(broken), checker.Semantics(broken)
    dp, ep = p.observe((0, 0), (1,), {})
    dq, eq = q.frame((0, 0), (1,), {})
    assert (dp, p.advance(ep, {})) != expected
    assert (dq, q.next_state(eq, {})) != expected
    return 1


def semantic_operator_tests() -> int:
    total = 0
    for width in range(1, 5):
        mask = (1 << width) - 1
        for a in range(1 << width):
            for b in range(1 << width):
                expected = {"and": a & b, "or": a | b, "xor": a ^ b,
                            "add": (a + b) & mask, "sub": (a - b) & mask,
                            "eq": int(a == b), "ult": int(a < b)}
                for name, value in expected.items():
                    e = [name, ["const", width, a], ["const", width, b]]
                    pn = producer.parse(e, {})
                    qw, code = checker.compile_expression(e, {})
                    assert pn.width == qw and producer.evaluate(pn, {}) == value and checker.execute(code, {}) == value
                    total += 1
            e = ["not", ["const", width, a]]
            assert producer.evaluate(producer.parse(e, {}), {}) == ((~a) & mask)
            _, code = checker.compile_expression(e, {})
            assert checker.execute(code, {}) == ((~a) & mask)
            total += 1
    return total


def check_bundle(raw: dict, b: dict, total: dict) -> dict:
    ans = checker.verify_bundle(raw, b, 100_000)
    add_work(total, "checker", ans["work"])
    assert ans["accepted"], (raw["id"], ans)
    return ans


def mutate_checks(models: dict[str, dict], bundles: dict, out: Path, total: dict) -> list[dict]:
    rows = []
    source = models["post-completion"]
    original = bundles[(source["id"], "first-hit")]

    def check(name, source_model, b, expected: bool):
        ans = checker.verify_bundle(source_model, b)
        add_work(total, "checker", ans["work"])
        assert ans["accepted"] == expected, (name, ans)
        rows.append({"mutation": name, "expected_accepted": expected,
                     "accepted": ans["accepted"], "reason": ans.get("reason", "valid certificate")})

    b = copy.deepcopy(original); b["preservation"]["frontiers"][0] = []
    check("missing-initial-pair", source, b, False)
    b = copy.deepcopy(original); b["preservation"]["frontiers"][1].pop()
    check("missing-live-successor", source, b, False)
    b = copy.deepcopy(original); b["preservation"]["horizon"] -= 1
    check("shorter-horizon", source, b, False)
    b = copy.deepcopy(original); b["preservation"]["retained"] = []
    check("unsafe-retained-set", source, b, False)
    b = copy.deepcopy(original); b["preservation"]["retained"] = ["r:nonexistent"]
    check("unknown-equation", source, b, False)
    b = copy.deepcopy(original); b["preservation"]["frontiers"][0][0][0][0] = False
    check("Boolean-in-state-integer", source, b, False)
    b = copy.deepcopy(original); b["necessities"] = []
    check("missing-necessity", source, b, False)
    b = copy.deepcopy(original); b["necessities"].append(copy.deepcopy(b["necessities"][0]))
    check("duplicate-necessity", source, b, False)
    b = copy.deepcopy(original); b["necessities"][0]["witness"]["retained"] = b["preservation"]["retained"]
    check("wrong-deletion-context", source, b, False)
    b = copy.deepcopy(original); b["timing_model"]["registers"][0]["next"] = ["const", 2, 0]
    check("tampered-timing-program", source, b, False)
    b = copy.deepcopy(original); b["timing_model"]["horizon"] -= 1
    check("timing-program-horizon", source, b, False)
    raw = copy.deepcopy(source); raw["registers"][0]["init"] = 1
    check("changed-source-initial-state", raw, original, False)
    raw = copy.deepcopy(source); raw["done"] = ["foreign_operator"]
    check("unsupported-source-operator", raw, original, False)
    b = copy.deepcopy(original); b["necessities"][0]["witness"].pop("predecessors")
    check("replay-only-canonicality", source, b, False)

    for case, alter in [("wire-width", "input"), ("wrap-counter", "cut")]:
        raw = models[case]
        b = copy.deepcopy(bundles[(case, "first-hit")])
        wit = b["necessities"][0]["witness"]
        if alter == "input": wit["inputs"][0][0] = 1
        else: wit["cuts"][0]["r:q"] = 2
        meter = checker.Meter()
        checker.replay(checker.Semantics(raw), wit, meter)
        add_work(total, "checker", meter.result())
        check("replayable-nonleast-" + alter, raw, b, False)
        write_json(out / ("noncanonical-" + alter + ".json"), b)

    # An overapproximating certificate may be valid: mutation != mandatory rejection.
    raw = models["never-complete"]
    b = copy.deepcopy(bundles[(raw["id"], "first-hit")])
    all_pairs = [[[s], [a]] for s in (0, 1) for a in (0, 1)]
    b["preservation"]["frontiers"] = [copy.deepcopy(all_pairs) for _ in range(raw["horizon"] + 1)]
    check("sound-frontier-superset", raw, b, True)
    ans = checker.verify_bundle(source, original, 0)
    assert not ans["accepted"] and ans["status"] == "unknown"
    rows.append({"mutation": "checker-budget-zero", "expected_accepted": False,
                 "accepted": False, "reason": "UNKNOWN, not a proof verdict"})
    ans = producer.bundle(producer.Model(source), limit=0)
    assert ans["status"] == "unknown"
    rows.append({"mutation": "producer-budget-zero", "expected_accepted": False,
                 "accepted": False, "reason": "UNKNOWN, not a proof verdict"})
    return rows


def run(out: Path) -> dict:
    raw_controls = cases.controls()
    all_reductions = cases.reductions()
    # Bind the readable stored fixtures to the exact generated experiment inputs.
    all_models = raw_controls + [raw for raw, _ in all_reductions]
    fixture_root = Path(__file__).resolve().parent / "cases"
    assert {p.name for p in fixture_root.glob("*.json")} == {raw["id"] + ".json" for raw in all_models}
    for raw in all_models:
        stored = json.loads((fixture_root / (raw["id"] + ".json")).read_text(),
                            object_pairs_hook=checker.strict_pairs)
        assert stored == raw, (raw["id"], "stored fixture and generator disagree")
    models = {m["id"]: m for m in raw_controls}
    total = {"producer": 0, "checker": 0, "closed_form_oracle": 0}
    units = semantic_tests(raw_controls)
    operators = semantic_operator_tests()
    retained_regression = retained_equation_regression(raw_controls)
    total["closed_form_oracle"] += units + operators + retained_regression
    bundles = {}
    controls = []
    witnesses = 0
    for raw in raw_controls:
        m = producer.Model(raw)
        for mode in ("first-hit", "waveform"):
            b = producer.bundle(m, mode)
            assert b["status"] == "inclusion-minimal", (m.raw["id"], b["status"])
            add_work(total, "producer", b["work"])
            checked = check_bundle(raw, b, total)
            bundles[(raw["id"], mode)] = b
            write_json(out / "bundles" / (raw["id"] + "-" + mode + ".json"), b)
            for necessity in b["necessities"]:
                w = necessity["witness"]
                oracle, count = oracles.exhaustive_witness(raw, set(w["retained"]), mode, w["time"])
                total["closed_form_oracle"] += count
                assert oracle is not None
                assert all(oracle[k] == w[k] for k in ("time", "inputs", "cuts")), (raw["id"], w, oracle)
                witnesses += 1
            emitted = producer.Model(b["timing_model"])
            controls.append({"case": raw["id"], "observation": mode,
                             "candidates": len(m.candidates), "retained": len(b["preservation"]["retained"]),
                             "retained_ids": ";".join(b["preservation"]["retained"]),
                             "source_registers": len(raw["registers"]),
                             "timing_registers": len(b["timing_model"]["registers"]),
                             "source_nodes": m.nodes, "timing_nodes": emitted.nodes,
                             "frontier_entries": sum(len(x) for x in b["preservation"]["frontiers"]),
                             "preservation_obligations": "",
                             "bundle_checker_obligations": checked["work"]["observations"] + checked["work"]["successors"]})
            pm = checker.Meter()
            checker.preservation(checker.Semantics(raw), b["preservation"], pm)
            add_work(total, "checker", pm.result())
            controls[-1]["preservation_obligations"] = pm.observations + pm.successors
    write_csv(out / "control_results.csv", controls)

    reductions = []
    classes = []
    for raw, meta in all_reductions:
        m = producer.Model(raw)
        cm = checker.Semantics(raw)
        true_keeps = []
        for bits in range(1 << len(m.candidates)):
            keep = {name for j, name in enumerate(m.candidates) if (bits >> j) & 1}
            free = [name for name in m.candidates if name not in keep]
            expected, witness, count = oracles.reduction_oracle(meta, [d["values"] for d in raw["inputs"]], free)
            total["closed_form_oracle"] += count
            pb = producer.Budget()
            answer = producer.search(m, keep, budget=pb)
            assert answer["status"] == ("valid" if expected else "invalid"), (raw["id"], keep)
            cert = answer["certificate"]
            meter = checker.Meter()
            if expected:
                checker.preservation(cm, cert, meter)
                true_keeps.append(keep)
            else:
                cert["predecessors"] = producer.predecessor_certificate(m, cert, pb)
                checker.canonical(cm, cert, meter)
                u, vals = witness
                assert cert["time"] == 0 and tuple(cert["inputs"][0]) == u
                assert tuple(cert["cuts"][0][n] for n in free) == vals
            add_work(total, "producer", pb.snapshot())
            add_work(total, "checker", meter.result())
            reductions.append({"case": raw["id"], "family": meta["family"],
                               "retained": ";".join(sorted(keep)), "expected": "valid" if expected else "invalid",
                               "observed": answer["status"], "certificate_checked": True})
        if meta["family"] == "validity":
            observed = set() in true_keeps
            expected = meta["mask"] == 0
        elif meta["family"] == "minimality":
            observed = {"w:r"} in true_keeps and set() not in true_keeps
            expected = meta["phi"] == 0 and meta["psi"] != 0
        else:
            observed = any(len(k) <= meta["n"] for k in true_keeps)
            expected = oracles.quantified_choice(meta)
        assert observed == expected, (raw["id"], "reduction theorem condition")
        classes.append({"case": raw["id"], "family": meta["family"],
                        "expected_condition": expected, "observed_condition": observed})
    write_csv(out / "reduction_results.csv", reductions)
    write_csv(out / "reduction_conditions.csv", classes)

    mutations = mutate_checks(models, bundles, out / "mutations", total)
    write_csv(out / "mutation_results.csv", mutations)

    # Mechanism controls. The fixed-zero relation is evaluated concretely, not
    # substituted into the havoc theorem.
    z = producer.Model(models["zero-cancellation"])
    zero_relation = []
    for bits in range(4):
        keep = {name for j, name in enumerate(z.candidates) if (bits >> j) & 1}
        emitted = producer.Model(producer.emit_model(z, keep))
        ds, _ = z.observe((), ())
        da, _ = emitted.observe((), ())
        zero_relation.append({"retained": ";".join(sorted(keep)), "zero_fill_preserved": ds == da})
    assert [x["zero_fill_preserved"] for x in zero_relation] == [True, False, False, True]
    write_csv(out / "zero_fill_nonmonotonicity.csv", zero_relation)
    joint = producer.Model(models["joint-omission"])
    for keep, expected in [({"w:a"}, "valid"), ({"w:b"}, "valid"), (set(), "invalid")]:
        ans = producer.search(joint, keep)
        add_work(total, "producer", ans["work"])
        assert ans["status"] == expected
    gap = bundles[("minimum-gap", "first-hit")]
    assert gap["preservation"]["retained"] == ["w:b", "w:c"]
    ans = producer.search(producer.Model(models["minimum-gap"]), {"w:a"})
    add_work(total, "producer", ans["work"])
    assert ans["status"] == "valid"
    comparisons = []
    for t in range(models["post-completion"]["horizon"] + 1):
        comparisons.append({"cycle": t,
            "first_hit_frontier": len(bundles[("post-completion", "first-hit")]["preservation"]["frontiers"][t]),
            "waveform_frontier": len(bundles[("post-completion", "waveform")]["preservation"]["frontiers"][t])})
    write_csv(out / "post_completion_frontiers.csv", comparisons)
    # Diagnostic repair: distinguish stopping on first completion from the
    # larger nondeterministic state set introduced by a smaller retained set.
    raw = models["post-completion"]
    m = producer.Model(raw)
    baseline = producer.search(m, set(m.candidates), "first-hit")
    add_work(total, "producer", baseline["work"])
    assert baseline["status"] == "valid"
    pm = checker.Meter()
    checker.preservation(checker.Semantics(raw), baseline["certificate"], pm)
    add_work(total, "checker", pm.result())
    write_json(out / "baselines" / "post-completion-unsliced-first-hit.json", baseline["certificate"])
    baseline_rows = [{"configuration": "unsliced-first-hit", "retained": len(m.candidates),
                      "frontier_entries": sum(len(f) for f in baseline["certificate"]["frontiers"]),
                      "preservation_obligations": pm.observations + pm.successors}]
    assert [len(f) for f in baseline["certificate"]["frontiers"]] == [1, 2, 2, 0, 0]
    for mode in ("first-hit", "waveform"):
        row = next(r for r in controls if r["case"] == "post-completion" and r["observation"] == mode)
        baseline_rows.append({"configuration": "sliced-" + mode,
                              **{key: row[key] for key in ("retained", "frontier_entries", "preservation_obligations")}})
    write_csv(out / "post_completion_baselines.csv", baseline_rows)

    # Explicitly account for each category of executed finite semantic work.
    # This is deliberately stricter than merely counting 928 top-level queries.
    total["closed_form_oracle"] += len(zero_relation)  # one paired observation per row
    work = sum(total.values())
    assert work < 70_000, ("pilot would consume repair/reproduction reserve", total)
    summary = {"pilot_status": "PASS", "research_gate": "HOLD",
        "public_rtl_modules": 0, "generated_control_models": len(raw_controls),
        "generated_reduction_models": len(all_reductions),
        "unique_generated_models": len(raw_controls) + len(all_reductions),
        "stored_fixture_models_matched": len(all_models),
        "control_bundles_checked": len(controls), "closed_form_transition_pairs": units,
        "operator_value_checks": operators, "retained_equation_regression_checks": retained_regression,
        "fixed_retained_set_baselines_checked": 1, "canonical_control_witnesses_checked": witnesses,
        "reduction_subset_queries": len(reductions), "reduction_conditions_checked": len(classes),
        "mutation_checks": len(mutations),
        "invalid_mutations_rejected": sum(not x["accepted"] and "budget" not in x["mutation"] for x in mutations),
        "sound_superset_accepted": True, "unknown_budget_controls": 2,
        "semantic_work": total, "total_semantic_work": work,
        "wider_choice_masks": cases.wider_masks(),
        "claims_not_established": ["novelty over the exact anchor and closest literature",
            "Verilog-to-IR semantic preservation", "public accelerator applicability",
            "unbounded-cycle equivalence", "minimum-cardinality optimizer", "RTL-simulator speedup",
            "mechanized proof of the checker", "complete venue calibration", "TCAD readiness"]}
    write_json(out / "summary.json", summary)
    return summary


def main() -> int:
    # POSIX limits belong to this CLI, not to the importable finite helpers.
    import resource
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists() and any(args.out.iterdir()):
        parser.error("output directory is nonempty; choose a fresh evidence directory")
    args.out.mkdir(parents=True, exist_ok=True)
    # One process, <=1 GiB address space, 90 CPU seconds, 118 wall seconds.
    resource.setrlimit(resource.RLIMIT_AS, (1024 ** 3, 1024 ** 3))
    resource.setrlimit(resource.RLIMIT_CPU, (90, 95))
    def timeout(signum, frame): raise TimeoutError("118-second wall limit")
    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(118)
    start, cpu = time.perf_counter(), time.process_time()
    code = 0
    failure = None
    try:
        summary = run(args.out)
        print(json.dumps(summary, indent=2, sort_keys=True))
    except Exception as e:
        code = 1
        failure = repr(e)
        print(failure, file=sys.stderr)
    finally:
        signal.alarm(0)
        record = {"command": "python3 reproduce.py --out " + str(args.out),
                  "exit_code": code, "wall_seconds": time.perf_counter() - start,
                  "cpu_seconds": time.process_time() - cpu,
                  "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                  "worker_processes": 1, "cpu_limit_seconds": 90,
                  "address_space_limit_bytes": 1024 ** 3, "failure": failure}
        write_json(args.out / "run.json", record)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
