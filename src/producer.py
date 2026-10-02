"""Search and emit bounded equation-cut timing certificates.

This module is untrusted by checker.py.  It uses only Python's standard library.
The input is an explicitly typed RTL-equation IR, not arbitrary Verilog.
"""
from __future__ import annotations

import argparse
import copy
import itertools
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


class ModelError(ValueError):
    pass


class LimitReached(RuntimeError):
    pass


@dataclass
class Budget:
    limit: int = 100_000
    observations: int = 0
    successors: int = 0

    def tick(self, successor: bool = False) -> None:
        if self.observations + self.successors >= self.limit:
            raise LimitReached("explicit semantic-obligation budget exhausted")
        if successor:
            self.successors += 1
        else:
            self.observations += 1

    def snapshot(self) -> dict[str, int]:
        return {"observations": self.observations, "successors": self.successors,
                "limit": self.limit}


@dataclass(frozen=True)
class Node:
    op: str
    width: int
    args: tuple[Any, ...]


def integer(x: Any, lo: int, hi: int, message: str) -> int:
    if type(x) is not int or not lo <= x <= hi:
        raise ModelError(message)
    return x


def parse(e: Any, names: dict[str, int], depth: int = 0) -> Node:
    if depth > 64 or type(e) is not list or not e or type(e[0]) is not str:
        raise ModelError("malformed/deep expression")
    op = e[0]
    if op == "const" and len(e) == 3:
        w = integer(e[1], 1, 16, "constant width")
        v = integer(e[2], 0, (1 << w) - 1, "constant value")
        return Node(op, w, (v,))
    if op == "var" and len(e) == 2 and type(e[1]) is str and e[1] in names:
        return Node(op, names[e[1]], (e[1],))
    arities = {"not": 1, "and": 2, "or": 2, "xor": 2, "add": 2, "sub": 2,
               "eq": 2, "ult": 2, "mux": 3, "concat": 2}
    if op == "slice" and len(e) == 4:
        a = parse(e[1], names, depth + 1)
        lo = integer(e[2], 0, a.width - 1, "slice low bit")
        w = integer(e[3], 1, a.width - lo, "slice width")
        return Node(op, w, (a, lo))
    if op not in arities or len(e) != arities[op] + 1:
        raise ModelError("unknown operator/arity: " + op)
    args = tuple(parse(a, names, depth + 1) for a in e[1:])
    if op == "mux":
        if args[0].width != 1 or args[1].width != args[2].width:
            raise ModelError("mux types")
        w = args[1].width
    elif op == "concat":
        w = args[0].width + args[1].width
        if w > 16:
            raise ModelError("concatenation width")
    elif op == "not":
        w = args[0].width
    else:
        if args[0].width != args[1].width:
            raise ModelError("binary operand widths")
        w = 1 if op in ("eq", "ult") else args[0].width
    return Node(op, w, args)


def evaluate(n: Node, env: dict[str, int]) -> int:
    if n.op == "const":
        return n.args[0]
    if n.op == "var":
        return env[n.args[0]]
    a = evaluate(n.args[0], env)
    if n.op == "slice":
        v = a >> n.args[1]
    elif n.op == "not":
        v = ~a
    else:
        b = evaluate(n.args[1], env)
        if n.op == "and": v = a & b
        elif n.op == "or": v = a | b
        elif n.op == "xor": v = a ^ b
        elif n.op == "add": v = a + b
        elif n.op == "sub": v = a - b
        elif n.op == "eq": v = int(a == b)
        elif n.op == "ult": v = int(a < b)
        elif n.op == "concat": v = (a << n.args[1].width) | b
        elif n.op == "mux": v = b if a else evaluate(n.args[2], env)
        else: raise ModelError("unreachable operator")
    return v & ((1 << n.width) - 1)


def node_count(e: list) -> int:
    return 1 + sum(node_count(x) for x in e[1:] if isinstance(x, list))


class Model:
    def __init__(self, raw: dict[str, Any]):
        if type(raw) is not dict or set(raw) != {
                "id", "inputs", "registers", "wires", "done", "horizon"}:
            raise ModelError("model keys")
        raw = copy.deepcopy(raw)
        self.raw = raw
        if type(raw["id"]) is not str or not raw["id"]:
            raise ModelError("model id")
        self.horizon = integer(raw["horizon"], 0, 64, "horizon")
        names: dict[str, int] = {}
        for key, cap in (("inputs", 16), ("registers", 128), ("wires", 512)):
            if type(raw[key]) is not list or len(raw[key]) > cap:
                raise ModelError(key + " list")
        for key in ("inputs", "registers"):
            for d in raw[key]:
                required = ({"name", "width", "values"} if key == "inputs" else
                            {"name", "width", "init", "next", "cut"})
                if type(d) is not dict or set(d) != required:
                    raise ModelError(key + " declaration")
                self._declare(d, names)
                if key == "inputs":
                    vv = d["values"]
                    if type(vv) is not list or not vv or any(type(x) is not int for x in vv):
                        raise ModelError("input domain")
                    if sorted(set(vv)) != vv:
                        raise ModelError("input values must be strictly increasing")
                    for v in vv: integer(v, 0, (1 << d["width"]) - 1, "input value")
                else:
                    integer(d["init"], 0, (1 << d["width"]) - 1, "initial value")
                    if type(d["cut"]) is not bool: raise ModelError("cut flag")
        self.wires: list[tuple[dict, Node]] = []
        for d in raw["wires"]:
            if type(d) is not dict or set(d) != {"name", "width", "expr", "cut"}:
                raise ModelError("wire declaration")
            if type(d["cut"]) is not bool: raise ModelError("cut flag")
            n = parse(d["expr"], names)
            self._declare(d, names)  # wires may refer only to previous wires
            if n.width != d["width"]: raise ModelError("wire width")
            self.wires.append((d, n))
        self.regs = []
        for d in raw["registers"]:
            n = parse(d["next"], names)
            if n.width != d["width"]: raise ModelError("next-state width")
            self.regs.append((d, n))
        self.done = parse(raw["done"], names)
        if self.done.width != 1: raise ModelError("done must have width one")
        self.widths = names
        exprs = [raw["done"]] + [d["expr"] for d, _ in self.wires] + [d["next"] for d, _ in self.regs]
        self.nodes = sum(node_count(e) for e in exprs)
        if self.nodes > 512: raise ModelError("expression-node ceiling")
        self.initial = tuple(d["init"] for d, _ in self.regs)
        self.candidates = tuple(["w:" + d["name"] for d, _ in self.wires if d["cut"]] +
                                ["r:" + d["name"] for d, _ in self.regs if d["cut"]])

    @staticmethod
    def _declare(d: dict, names: dict[str, int]) -> None:
        name = d.get("name")
        if type(name) is not str or not name or not name.isascii() or not name.isidentifier() or name in names:
            raise ModelError("duplicate/invalid identifier")
        names[name] = integer(d["width"], 1, 16, "signal width")

    def inputs(self) -> Iterable[tuple[int, ...]]:
        return itertools.product(*(d["values"] for d in self.raw["inputs"]))

    def cuts(self, retained: set[str], wire: bool) -> list[tuple[str, int]]:
        ds = self.wires if wire else self.regs
        prefix = "w:" if wire else "r:"
        return [(prefix + d["name"], d["width"]) for d, _ in ds
                if d["cut"] and prefix + d["name"] not in retained]

    def observe(self, state: tuple[int, ...], u: tuple[int, ...],
                cuts: dict[str, int] | None = None) -> tuple[int, dict[str, int]]:
        cuts = cuts or {}
        env = {d["name"]: v for d, v in zip(self.raw["inputs"], u)}
        env.update({d["name"]: v for (d, _), v in zip(self.regs, state)})
        for d, n in self.wires:
            key = "w:" + d["name"]
            env[d["name"]] = cuts[key] if key in cuts else evaluate(n, env)
        return evaluate(self.done, env), env

    def advance(self, env: dict[str, int], cuts: dict[str, int] | None = None) -> tuple[int, ...]:
        cuts = cuts or {}
        return tuple(cuts["r:" + d["name"]] if "r:" + d["name"] in cuts
                     else evaluate(n, env) for d, n in self.regs)


def assignments(ds: list[tuple[str, int]]) -> Iterable[tuple[int, ...]]:
    return itertools.product(*(range(1 << w) for _, w in ds))


def pack_frontier(frontier: Iterable[tuple]) -> list:
    return [[list(s), list(a)] for s, a in sorted(frontier)]


def search(model: Model, retained: set[str], observation: str = "first-hit",
           budget: Budget | None = None) -> dict[str, Any]:
    """Exact layered search; merge equal product states using the least history.

    Canonical order: difference cycle, entire input prefix, entire cut prefix.
    A cut prefix lists wire cuts before next-state cuts at each earlier cycle;
    the final cycle lists wire cuts only.
    """
    budget = budget or Budget()
    if not retained <= set(model.candidates): raise ModelError("unknown retained equation")
    if observation not in ("first-hit", "waveform"): raise ModelError("observation mode")
    wc, rc = model.cuts(retained, True), model.cuts(retained, False)
    frontier = {(model.initial, model.initial): ((), ())}
    layers = []
    try:
        for t in range(model.horizon + 1):
            layers.append(pack_frontier(frontier))
            nxt: dict[tuple, tuple] = {}
            bad: tuple | None = None
            for (s, a), (ip, cp) in sorted(frontier.items()):
                for u in model.inputs():
                    ds, es = model.observe(s, u)
                    ns = model.advance(es) if t < model.horizon else ()
                    for wv in assignments(wc):
                        budget.tick()
                        dm = dict(zip((k for k, _ in wc), wv))
                        da, ea = model.observe(a, u, dm)
                        ih = ip + (u,)
                        if ds != da:
                            history = (ih, cp + (wv,))
                            if bad is None or history < bad: bad = history
                            continue
                        if t == model.horizon or (observation == "first-hit" and ds):
                            continue
                        for rv in assignments(rc):
                            budget.tick(True)
                            na = model.advance(ea, dict(zip((k for k, _ in rc), rv)))
                            history = (ih, cp + (wv + rv,))
                            state = (ns, na)
                            if state not in nxt or history < nxt[state]: nxt[state] = history
            if bad is not None:
                ip, cp = bad
                steps = []
                for j, vals in enumerate(cp):
                    fields = wc + (rc if j < t else [])
                    steps.append(dict(zip((k for k, _ in fields), vals)))
                return {"status": "invalid", "certificate": {
                    "kind": "counterexample", "retained": sorted(retained),
                    "horizon": model.horizon, "observation": observation,
                    "time": t, "inputs": [list(x) for x in ip], "cuts": steps},
                    "work": budget.snapshot()}
            frontier = nxt
            if len(frontier) > 50_000: raise LimitReached("frontier-size ceiling")
        return {"status": "valid", "certificate": {
            "kind": "preservation", "retained": sorted(retained),
            "horizon": model.horizon, "observation": observation,
            "frontiers": layers}, "work": budget.snapshot()}
    except LimitReached as e:
        return {"status": "unknown", "reason": str(e), "work": budget.snapshot()}


def compare(a: tuple, b: tuple) -> int:
    return (a > b) - (a < b)


def signed(old: int, a: tuple, b: tuple) -> int:
    return old if old else compare(a, b)


def predecessor_certificate(model: Model, witness: dict, budget: Budget | None = None) -> dict:
    """Certify exclusion of every shorter or lexicographically smaller witness.

    Four-coordinate frontiers store two machine states and two prefix-order
    signs. This is not merely a replay of the supplied witness.
    """
    budget = budget or Budget()
    retained = set(witness["retained"])
    wc, rc = model.cuts(retained, True), model.cuts(retained, False)
    d = witness["time"]
    frontier = {(model.initial, model.initial, 0, 0)}
    layers = []
    for t in range(d + 1):
        layers.append([[list(s), list(a), i, j] for s, a, i, j in sorted(frontier)])
        nxt = set()
        target_u = tuple(witness["inputs"][t])
        fields = wc + (rc if t < d else [])
        target_c = tuple(witness["cuts"][t][k] for k, _ in fields)
        for s, a, si, sj in frontier:
            for u in model.inputs():
                ds, es = model.observe(s, u)
                ii = signed(si, u, target_u)
                for wv in assignments(wc):
                    budget.tick()
                    da, ea = model.observe(a, u, dict(zip((k for k, _ in wc), wv)))
                    if ds != da and t < d:
                        raise ModelError("witness is not shortest")
                    if t == d:
                        jj = signed(sj, wv, target_c)
                        if ds != da and (ii < 0 or (ii == 0 and jj < 0)):
                            raise ModelError("witness is not lexicographically least")
                        continue
                    if witness["observation"] == "first-hit" and ds:
                        continue
                    ns = model.advance(es)
                    for rv in assignments(rc):
                        budget.tick(True)
                        jj = signed(sj, wv + rv, target_c)
                        na = model.advance(ea, dict(zip((k for k, _ in rc), rv)))
                        nxt.add((ns, na, ii, jj))
        frontier = nxt
        if len(frontier) > 50_000: raise LimitReached("predecessor frontier ceiling")
    return {"frontiers": layers}


def _fold(e: list, constants: dict[str, list]) -> list:
    if e[0] == "var": return copy.deepcopy(constants.get(e[1], e))
    if e[0] == "const": return list(e)
    z = [e[0]] + [_fold(x, constants) if isinstance(x, list) else x for x in e[1:]]
    children = [x for x in z[1:] if isinstance(x, list)]
    if z[0] == "mux" and z[1][0] == "const": return z[2] if z[1][2] else z[3]
    if children and all(x[0] == "const" for x in children):
        n = parse(z, {})
        return ["const", n.width, evaluate(n, {})]
    return z


def references(e: list) -> set[str]:
    if e[0] == "var": return {e[1]}
    return set().union(*(references(x) for x in e[1:] if isinstance(x, list)))


def emit_model(model: Model, retained: set[str]) -> dict:
    """Zero-fill omitted equations, remove trivial constant registers and dead cone.

    This deterministic implementation is a member of the certified havoc model.
    The checker separately reconstructs and checks this transformation.
    """
    out = copy.deepcopy(model.raw)
    for d in out["wires"]:
        if d["cut"] and "w:" + d["name"] not in retained:
            d["expr"] = ["const", d["width"], 0]
        d["cut"] = False
    for d in out["registers"]:
        if d["cut"] and "r:" + d["name"] not in retained:
            d["next"] = ["const", d["width"], 0]
        d["cut"] = False
    constants = {d["name"]: d["next"] for d in out["registers"]
                 if d["next"] == ["const", d["width"], d["init"]]}
    removed = set(constants)
    for d in out["wires"]:
        d["expr"] = _fold(d["expr"], constants)
        if d["expr"][0] == "const": constants[d["name"]] = d["expr"]
    for d in out["registers"]: d["next"] = _fold(d["next"], constants)
    out["done"] = _fold(out["done"], constants)
    definitions = {d["name"]: d["expr"] for d in out["wires"]}
    definitions.update({d["name"]: d["next"] for d in out["registers"]})
    live = references(out["done"])
    queue = list(live)
    while queue:
        name = queue.pop()
        for dep in references(definitions[name]) if name in definitions else ():
            if dep not in live:
                live.add(dep)
                queue.append(dep)
    out["wires"] = [d for d in out["wires"] if d["name"] in live]
    out["registers"] = [d for d in out["registers"] if d["name"] in live and d["name"] not in removed]
    out["id"] += "-timing"
    Model(out)
    return out


def bundle(model: Model, observation: str = "first-hit", limit: int = 100_000) -> dict:
    """Greedy inclusion minimization with fresh final-context certificates."""
    budget = Budget(limit)
    k = set(model.candidates)
    attempts = []
    unknown = False
    for e in sorted(k):
        ans = search(model, k - {e}, observation, budget)
        attempts.append({"equation": e, "status": ans["status"]})
        if ans["status"] == "valid": k.remove(e)
        elif ans["status"] == "unknown": unknown = True
    final = search(model, k, observation, budget)
    if final["status"] != "valid":
        return {"status": "unknown", "attempts": attempts, "work": budget.snapshot()}
    necessities = []
    try:
        for e in sorted(k):
            ans = search(model, k - {e}, observation, budget)
            if ans["status"] != "invalid":
                unknown = True
                continue
            c = ans["certificate"]
            c["predecessors"] = predecessor_certificate(model, c, budget)
            necessities.append({"equation": e, "witness": c})
    except LimitReached:
        unknown = True
    return {"status": "preserved" if unknown else "inclusion-minimal",
            "model_id": model.raw["id"], "preservation": final["certificate"],
            "necessities": necessities, "timing_model": emit_model(model, k),
            "attempts": attempts, "work": budget.snapshot()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--limit", type=int, default=100_000)
    parser.add_argument("--observation", choices=["first-hit", "waveform"], default="first-hit")
    args = parser.parse_args()
    try:
        m = Model(json.loads(args.model.read_text()))
        ans = bundle(m, args.observation, args.limit)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(ans, indent=2, sort_keys=True) + "\n")
        print(ans["status"])
        return 2 if ans["status"] == "unknown" else 0
    except (ModelError, OSError, json.JSONDecodeError) as e:
        print(str(e))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
