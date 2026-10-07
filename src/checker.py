"""Stand-alone finite certificate checker. No producer/search imports.

The trusted semantic implementation uses typed stack programs, unlike the
producer's expression trees. Acceptance binds to the supplied source IR by
re-evaluating its equations, not to a name, digest, or solver verdict.
"""
from __future__ import annotations

import argparse
import copy
import itertools
import json
from pathlib import Path
from typing import Any


class Rejected(ValueError):
    pass


class Incomplete(RuntimeError):
    pass


class Meter:
    def __init__(self, limit: int = 100_000):
        self.limit = limit
        self.observations = 0
        self.successors = 0

    def use(self, edge: bool = False) -> None:
        if self.observations + self.successors >= self.limit:
            raise Incomplete("checker semantic-obligation limit")
        if edge: self.successors += 1
        else: self.observations += 1

    def result(self) -> dict:
        return {"observations": self.observations, "successors": self.successors,
                "limit": self.limit}


def require(condition: bool, text: str) -> None:
    if not condition: raise Rejected(text)


def number(x: Any, low: int, high: int) -> int:
    require(type(x) is int and low <= x <= high, "integer outside declared range")
    return x


def fields(x: Any, keys: set[str]) -> None:
    require(type(x) is dict and set(x) == keys, "unexpected or missing fields")


def compile_expression(expr: Any, widths: dict[str, int], depth: int = 0) -> tuple[int, list]:
    """Type-check an expression and emit a postorder stack program."""
    require(type(expr) is list and bool(expr) and depth <= 64, "bad expression")
    op = expr[0]
    require(type(op) is str, "operator must be a string")
    if op == "const":
        require(len(expr) == 3, "constant arity")
        width = number(expr[1], 1, 16)
        value = number(expr[2], 0, (1 << width) - 1)
        return width, [("const", width, value)]
    if op == "var":
        require(len(expr) == 2 and type(expr[1]) is str and expr[1] in widths,
                "unknown or forward variable")
        return widths[expr[1]], [("var", widths[expr[1]], expr[1])]
    if op == "slice":
        require(len(expr) == 4, "slice arity")
        aw, code = compile_expression(expr[1], widths, depth + 1)
        lo = number(expr[2], 0, aw - 1)
        width = number(expr[3], 1, aw - lo)
        return width, code + [("slice", width, lo)]
    if op in {"and", "or", "xor", "add", "sub", "eq", "ult", "concat"}: n = 2
    elif op == "not": n = 1
    elif op == "mux": n = 3
    else: raise Rejected("unsupported operator")
    require(len(expr) == n + 1, "operator arity")
    pieces = [compile_expression(a, widths, depth + 1) for a in expr[1:]]
    sizes = [p[0] for p in pieces]
    code = [instruction for _, p in pieces for instruction in p]
    extra = 0
    if op == "concat":
        width = sum(sizes)
        number(width, 1, 16)
        extra = sizes[1]
    elif op == "mux":
        require(sizes[0] == 1 and sizes[1] == sizes[2], "mux type mismatch")
        width = sizes[1]
    elif op == "not": width = sizes[0]
    else:
        require(sizes[0] == sizes[1], "unequal binary widths")
        width = 1 if op in {"eq", "ult"} else sizes[0]
    return width, code + [(op, width, extra)]


def execute(code: list, values: dict[str, int]) -> int:
    stack: list[int] = []
    for op, width, aux in code:
        mask = (1 << width) - 1
        if op == "const": stack.append(aux)
        elif op == "var": stack.append(values[aux])
        elif op == "slice": stack.append((stack.pop() >> aux) & mask)
        elif op == "not": stack.append((~stack.pop()) & mask)
        elif op == "mux":
            no = stack.pop()
            yes = stack.pop()
            condition = stack.pop()
            stack.append(yes if condition else no)
        else:
            right = stack.pop()
            left = stack.pop()
            if op == "add": value = left + right
            elif op == "sub": value = left - right
            elif op == "and": value = left & right
            elif op == "or": value = left | right
            elif op == "xor": value = left ^ right
            elif op == "eq": value = int(left == right)
            elif op == "ult": value = int(left < right)
            elif op == "concat": value = (left << aux) | right
            else: raise Rejected("bad stack program")
            stack.append(value & mask)
    require(len(stack) == 1, "stack did not produce one value")
    return stack[0]


class Semantics:
    def __init__(self, model: Any):
        fields(model, {"id", "inputs", "registers", "wires", "done", "horizon"})
        self.data = copy.deepcopy(model)
        model = self.data
        require(type(model["id"]) is str and bool(model["id"]), "model id")
        self.horizon = number(model["horizon"], 0, 64)
        self.widths: dict[str, int] = {}
        for name, cap in (("inputs", 16), ("registers", 128), ("wires", 512)):
            require(type(model[name]) is list and len(model[name]) <= cap, "declaration list")
        for d in model["inputs"]:
            fields(d, {"name", "width", "values"})
            self.declare(d)
            vals = d["values"]
            require(type(vals) is list and bool(vals), "empty input domain")
            for v in vals: number(v, 0, (1 << d["width"]) - 1)
            require(vals == sorted(set(vals)), "noncanonical input domain")
        for d in model["registers"]:
            fields(d, {"name", "width", "init", "next", "cut"})
            self.declare(d)
            number(d["init"], 0, (1 << d["width"]) - 1)
            require(type(d["cut"]) is bool, "register cut flag")
        self.wire_programs = []
        count = 0
        for d in model["wires"]:
            fields(d, {"name", "width", "expr", "cut"})
            require(type(d["cut"]) is bool, "wire cut flag")
            w, program = compile_expression(d["expr"], self.widths)
            self.declare(d)
            require(w == d["width"], "wire result width")
            self.wire_programs.append(program)
            count += len(program)
        self.next_programs = []
        for d in model["registers"]:
            w, program = compile_expression(d["next"], self.widths)
            require(w == d["width"], "register result width")
            self.next_programs.append(program)
            count += len(program)
        w, self.done_program = compile_expression(model["done"], self.widths)
        require(w == 1, "non-Boolean completion")
        count += len(self.done_program)
        require(count <= 512, "expression-node ceiling")
        self.initial = tuple(d["init"] for d in model["registers"])
        self.candidates = {p + d["name"] for key, p in (("wires", "w:"), ("registers", "r:"))
                           for d in model[key] if d["cut"]}

    def declare(self, d: dict) -> None:
        name = d["name"]
        require(type(name) is str and name.isascii() and name.isidentifier()
                and name not in self.widths, "invalid/duplicate identifier")
        self.widths[name] = number(d["width"], 1, 16)

    def domain(self):
        return itertools.product(*[d["values"] for d in self.data["inputs"]])

    def free(self, k: set[str], key: str) -> list[tuple[str, int]]:
        p = "w:" if key == "wires" else "r:"
        return [(p + d["name"], d["width"]) for d in self.data[key]
                if d["cut"] and p + d["name"] not in k]

    def frame(self, state: tuple, u: tuple, cut: dict) -> tuple[int, dict]:
        context = dict(zip([d["name"] for d in self.data["registers"]], state))
        context.update(dict(zip([d["name"] for d in self.data["inputs"]], u)))
        for index, d in enumerate(self.data["wires"]):
            context[d["name"]] = (cut["w:" + d["name"]] if "w:" + d["name"] in cut
                                  else execute(self.wire_programs[index], context))
        return execute(self.done_program, context), context

    def next_state(self, context: dict, cut: dict) -> tuple:
        answer = []
        for index, d in enumerate(self.data["registers"]):
            key = "r:" + d["name"]
            answer.append(cut[key] if key in cut else execute(self.next_programs[index], context))
        return tuple(answer)

    def state(self, x: Any) -> tuple:
        require(type(x) is list and len(x) == len(self.data["registers"]), "state shape")
        for v, d in zip(x, self.data["registers"]): number(v, 0, (1 << d["width"]) - 1)
        return tuple(x)

    def input(self, x: Any) -> tuple:
        require(type(x) is list and len(x) == len(self.data["inputs"]), "input shape")
        for v, d in zip(x, self.data["inputs"]):
            require(type(v) is int and v in d["values"], "input not in contract")
        return tuple(x)


def values(free: list[tuple[str, int]]):
    return itertools.product(*[range(2 ** width) for _, width in free])


def metadata(m: Semantics, c: dict) -> tuple[set[str], str]:
    require(type(c) is dict, "certificate metadata must be a mapping")
    require(type(c.get("horizon")) is int and c["horizon"] == m.horizon, "horizon mismatch")
    keep = c.get("retained")
    require(type(keep) is list and all(type(x) is str for x in keep), "retained list")
    require(keep == sorted(set(keep)) and set(keep) <= m.candidates, "retained identifiers")
    require(c.get("observation") in ("first-hit", "waveform"), "observation policy")
    return set(keep), c["observation"]


def frontiers(m: Semantics, rows: Any, depth: int, signs: bool = False) -> list[set]:
    require(type(rows) is list and len(rows) == depth + 1, "frontier depth mismatch")
    answer = []
    for layer in rows:
        require(type(layer) is list, "frontier is not a list")
        if len(layer) > 50_000: raise Incomplete("frontier representation limit")
        parsed = []
        for x in layer:
            require(type(x) is list and len(x) == (4 if signs else 2), "frontier row shape")
            row = (m.state(x[0]), m.state(x[1]))
            if signs: row += (number(x[2], -1, 1), number(x[3], -1, 1))
            parsed.append(row)
        require(parsed == sorted(set(parsed)), "duplicate or unsorted frontier")
        answer.append(set(parsed))
    return answer


def preservation(m: Semantics, c: Any, meter: Meter) -> None:
    fields(c, {"kind", "retained", "horizon", "observation", "frontiers"})
    require(c["kind"] == "preservation", "not a preservation certificate")
    k, observation = metadata(m, c)
    layers = frontiers(m, c["frontiers"], m.horizon)
    require((m.initial, m.initial) in layers[0], "initial pair omitted")
    wc, rc = m.free(k, "wires"), m.free(k, "registers")
    uncomputed = object()
    for t, layer in enumerate(layers):
        for pair in layer:
            for u in m.domain():
                ds, source = m.frame(pair[0], u, {})
                source_next = uncomputed
                for wv in values(wc):
                    meter.use()
                    cut = dict(zip([n for n, _ in wc], wv))
                    da, abstract = m.frame(pair[1], u, cut)
                    require(ds == da, f"completion mismatch at cycle {t}")
                    if t == m.horizon or (observation == "first-hit" and ds == 1): continue
                    for rv in values(rc):
                        meter.use(True)
                        cut.update(dict(zip([n for n, _ in rc], rv)))
                        if source_next is uncomputed:
                            source_next = m.next_state(source, {})
                        target = (source_next, m.next_state(abstract, cut))
                        require(target in layers[t + 1], "uncovered successor")


def replay(m: Semantics, c: dict, meter: Meter) -> tuple[set[str], str, int]:
    keys = {"kind", "retained", "horizon", "observation", "time", "inputs", "cuts"}
    require(type(c) is dict and set(c) in (keys, keys | {"predecessors"}), "witness fields")
    require(c["kind"] == "counterexample", "not a counterexample")
    k, observation = metadata(m, c)
    d = number(c["time"], 0, m.horizon)
    require(type(c["inputs"]) is list and type(c["cuts"]) is list
            and len(c["inputs"]) == d + 1 and len(c["cuts"]) == d + 1, "witness length")
    wc, rc = m.free(k, "wires"), m.free(k, "registers")
    s = a = m.initial
    for t in range(d + 1):
        u = m.input(c["inputs"][t])
        free = wc + (rc if t < d else [])
        cut = c["cuts"][t]
        require(type(cut) is dict and set(cut) == {name for name, _ in free}, "cut assignment fields")
        for name, width in free: number(cut[name], 0, (1 << width) - 1)
        meter.use()
        ds, se = m.frame(s, u, {})
        da, ae = m.frame(a, u, cut)
        if t == d:
            require(ds != da, "last sample does not differentiate")
        else:
            require(ds == da, "earlier mismatch than reported")
            require(not (observation == "first-hit" and ds), "witness continues after both complete")
            meter.use(True)
            s, a = m.next_state(se, {}), m.next_state(ae, cut)
    return k, observation, d


def order_sign(old: int, a: tuple, b: tuple) -> int:
    if old != 0: return old
    if a < b: return -1
    return int(a > b)


def canonical(m: Semantics, c: dict, meter: Meter) -> None:
    k, observation, d = replay(m, c, meter)
    require("predecessors" in c, "canonicality needs predecessor-exclusion evidence")
    fields(c["predecessors"], {"frontiers"})
    layers = frontiers(m, c["predecessors"]["frontiers"], d, True)
    require((m.initial, m.initial, 0, 0) in layers[0], "initial ordered pair omitted")
    wc, rc = m.free(k, "wires"), m.free(k, "registers")
    uncomputed = object()
    for t, layer in enumerate(layers):
        target_u = tuple(c["inputs"][t])
        free = wc + (rc if t < d else [])
        target_v = tuple(c["cuts"][t][n] for n, _ in free)
        for s, a, si, sj in layer:
            for u in m.domain():
                ds, se = m.frame(s, u, {})
                source_next = uncomputed
                sign_i = order_sign(si, u, target_u)
                for wv in values(wc):
                    meter.use()
                    cut = dict(zip([n for n, _ in wc], wv))
                    da, ae = m.frame(a, u, cut)
                    if t == d:
                        sign_c = order_sign(sj, wv, target_v)
                        smaller = sign_i == -1 or (sign_i == 0 and sign_c == -1)
                        require(not (ds != da and smaller), "a lexicographically smaller witness exists")
                        continue
                    require(ds == da, "a shorter witness exists")
                    if observation == "first-hit" and ds: continue
                    for rv in values(rc):
                        meter.use(True)
                        cut.update(dict(zip([n for n, _ in rc], rv)))
                        sign_c = order_sign(sj, wv + rv, target_v)
                        if source_next is uncomputed:
                            source_next = m.next_state(se, {})
                        target = (source_next, m.next_state(ae, cut), sign_i, sign_c)
                        require(target in layers[t + 1], "ordered-prefix successor omitted")


def _substitute(expr: list, constant: dict[str, list]) -> list:
    # Independently validate the emitter's restricted constant-folding language.
    if expr[0] == "const": return list(expr)
    if expr[0] == "var": return list(constant[expr[1]]) if expr[1] in constant else list(expr)
    changed = []
    all_literal = True
    for child in expr[1:]:
        if type(child) is list:
            new = _substitute(child, constant)
            changed.append(new)
            all_literal = all_literal and new[0] == "const"
        else: changed.append(child)
    result = [expr[0]] + changed
    if expr[0] == "mux" and changed[0][0] == "const":
        return changed[1] if changed[0][2] != 0 else changed[2]
    if all_literal:
        w, program = compile_expression(result, {})
        return ["const", w, execute(program, {})]
    return result


def _uses(expr: list) -> set[str]:
    todo = [expr]
    names = set()
    while todo:
        item = todo.pop()
        if item[0] == "var": names.add(item[1])
        else: todo.extend(x for x in item[1:] if type(x) is list)
    return names


def emitted_model(m: Semantics, keep: set[str], supplied: Any) -> None:
    """Bind the deterministic timing program to the certified equation cut."""
    expected = copy.deepcopy(m.data)
    constant = {}
    removed = set()
    for d in expected["registers"]:
        if d["cut"] and "r:" + d["name"] not in keep:
            d["next"] = ["const", d["width"], 0]
        d["cut"] = False
        if d["next"] == ["const", d["width"], d["init"]]:
            constant[d["name"]] = list(d["next"])
            removed.add(d["name"])
    for d in expected["wires"]:
        expr = (["const", d["width"], 0] if d["cut"] and "w:" + d["name"] not in keep else d["expr"])
        d["expr"] = _substitute(expr, constant)
        d["cut"] = False
        if d["expr"][0] == "const": constant[d["name"]] = list(d["expr"])
    for d in expected["registers"]: d["next"] = _substitute(d["next"], constant)
    expected["done"] = _substitute(expected["done"], constant)
    live = _uses(expected["done"])
    while True:
        before = set(live)
        for d in expected["registers"]:
            if d["name"] in live: live |= _uses(d["next"])
        for d in expected["wires"]:
            if d["name"] in live: live |= _uses(d["expr"])
        if live == before: break
    expected["registers"] = [d for d in expected["registers"] if d["name"] in live and d["name"] not in removed]
    expected["wires"] = [d for d in expected["wires"] if d["name"] in live]
    expected["id"] = m.data["id"] + "-timing"
    require(supplied == expected, "emitted timing program differs from the certified transformation")
    Semantics(supplied)


def verify_bundle(source: Any, b: Any, limit: int = 100_000) -> dict:
    meter = Meter(limit)
    try:
        fields(b, {"status", "model_id", "preservation", "necessities", "timing_model", "attempts", "work"})
        m = Semantics(source)
        require(b["model_id"] == m.data["id"], "source label mismatch")
        require(b["status"] in ("inclusion-minimal", "preserved"), "uncertified bundle status")
        preservation(m, b["preservation"], meter)
        keep, _ = metadata(m, b["preservation"])
        require(type(b["necessities"]) is list, "necessity list")
        covered = set()
        for row in b["necessities"]:
            fields(row, {"equation", "witness"})
            e = row["equation"]
            require(type(e) is str and e in keep and e not in covered, "necessity equation")
            other, obs = metadata(m, row["witness"])
            require(other == keep - {e} and obs == b["preservation"]["observation"], "wrong deletion context")
            canonical(m, row["witness"], meter)
            covered.add(e)
        if b["status"] == "inclusion-minimal":
            require(covered == keep, "some retained equation lacks a necessity witness")
        emitted_model(m, keep, b["timing_model"])
        return {"accepted": True, "claim": b["status"], "work": meter.result()}
    except Incomplete as e:
        return {"accepted": False, "status": "unknown", "reason": str(e), "work": meter.result()}
    except (Rejected, KeyError, TypeError, IndexError, RecursionError) as e:
        return {"accepted": False, "status": "rejected", "reason": str(e), "work": meter.result()}


def strict_pairs(pairs: list[tuple]) -> dict:
    answer = {}
    for key, val in pairs:
        require(key not in answer, "duplicate JSON key")
        answer[key] = val
    return answer


def load(path: Path) -> Any:
    if path.stat().st_size > 16 * 1024 * 1024: raise Incomplete("input file larger than checker envelope")
    return json.loads(path.read_text(), object_pairs_hook=strict_pairs)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("model", type=Path)
    ap.add_argument("bundle", type=Path)
    ap.add_argument("--limit", type=int, default=100_000)
    args = ap.parse_args()
    try:
        answer = verify_bundle(load(args.model), load(args.bundle), args.limit)
    except (Rejected, Incomplete, OSError, json.JSONDecodeError) as e:
        answer = {"accepted": False, "status": "unknown" if isinstance(e, Incomplete) else "rejected", "reason": str(e)}
    print(json.dumps(answer, sort_keys=True))
    return 0 if answer.get("accepted") else (2 if answer.get("status") == "unknown" else 1)


if __name__ == "__main__":
    raise SystemExit(main())
