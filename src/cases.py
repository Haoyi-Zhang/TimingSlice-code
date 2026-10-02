"""Deterministic, deliberately small semantic fixtures and reduction instances.

These are generated equation systems, not public accelerator benchmarks.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path


def c(width: int, value: int): return ["const", width, value]
def v(name: str): return ["var", name]
def op(name: str, *args): return [name, *args]
def inp(name: str, width: int = 1):
    return {"name": name, "width": width, "values": list(range(1 << width))}
def reg(name: str, width: int, initial: int, expr, cut: bool = True):
    return {"name": name, "width": width, "init": initial, "next": expr, "cut": cut}
def wire(name: str, width: int, expr, cut: bool = True):
    return {"name": name, "width": width, "expr": expr, "cut": cut}
def model(name: str, inputs, registers, wires, done, horizon: int):
    return {"id": name, "inputs": inputs, "registers": registers,
            "wires": wires, "done": done, "horizon": horizon}


def combine(operator: str, exprs: list, identity: int):
    if not exprs: return c(1, identity)
    if len(exprs) == 1: return exprs[0]
    middle = len(exprs) // 2
    return op(operator, combine(operator, exprs[:middle], identity),
              combine(operator, exprs[middle:], identity))


def truth_table(mask: int, names: list[str]):
    """Bit index is the big-endian valuation of names; bit=1 means true."""
    terms = []
    for index in range(1 << len(names)):
        if mask & (1 << index):
            literals = [v(name) if (index >> (len(names) - j - 1)) & 1
                        else op("not", v(name)) for j, name in enumerate(names)]
            terms.append(combine("and", literals, 1))
    return combine("or", terms, 0)


def controls():
    result = []
    result.append(model("joint-omission", [], [],
        [wire("a", 1, c(1, 0)), wire("b", 1, c(1, 0))],
        op("and", v("a"), v("b")), 0))
    result.append(model("zero-cancellation", [], [],
        [wire("a", 1, c(1, 1)), wire("b", 1, c(1, 1))],
        op("xor", v("a"), v("b")), 0))
    phase = op("mux", op("eq", v("phase"), c(2, 3)), c(2, 3), op("add", v("phase"), c(2, 1)))
    done = op("mux", op("eq", v("phase"), c(2, 2)), c(1, 1),
              op("and", op("eq", v("phase"), c(2, 3)),
                 op("xor", v("flag"), op("slice", v("payload"), 0, 1))))
    result.append(model("post-completion", [inp("x")],
        [reg("phase", 2, 0, phase), reg("flag", 1, 0, v("x")),
         reg("payload", 2, 0, op("add", v("payload"), c(2, 1)))], [], done, 4))
    result.append(model("enable-counter", [inp("enable")],
        [reg("q", 2, 0, op("mux", v("gate"), op("add", v("q"), c(2, 1)), v("q")))],
        [wire("gate", 1, v("enable"))], op("eq", v("q"), c(2, 3)), 4))
    result.append(model("reset-counter", [inp("reset"), inp("enable")],
        [reg("q", 2, 0, op("mux", v("rst"), c(2, 0),
               op("mux", v("enable"), op("add", v("q"), c(2, 1)), v("q"))))],
        [wire("rst", 1, v("reset"))], op("eq", v("q"), c(2, 2)), 3))
    result.append(model("old-value-pipeline", [inp("go")],
        [reg("a", 1, 0, v("go")), reg("b", 1, 0, v("a"))], [], v("b"), 3))
    result.append(model("wrap-counter", [],
        [reg("q", 2, 3, op("add", v("q"), c(2, 1)))], [], op("eq", v("q"), c(2, 0)), 4))
    result.append(model("never-complete", [],
        [reg("q", 1, 0, op("not", v("q")))], [], c(1, 0), 3))
    result.append(model("initial-completion", [inp("x")],
        [reg("q", 1, 1, v("x"))], [], v("q"), 3))
    result.append(model("wire-width", [inp("x", 2)], [],
        [wire("w", 2, op("add", v("x"), c(2, 1)))], op("eq", v("w"), c(2, 0)), 1))
    result.append(model("concat-slice", [inp("lo"), inp("hi")], [],
        [wire("joined", 2, op("concat", v("hi"), v("lo"))),
         wire("top", 1, op("slice", v("joined"), 1, 1))], v("top"), 1))
    result.append(model("shared-wire", [inp("x")], [],
        [wire("a", 1, v("x"))], op("xor", v("a"), v("a")), 2))
    result.append(model("minimum-gap", [], [],
        [wire("a", 1, c(1, 0)), wire("b", 1, c(1, 0)), wire("c", 1, c(1, 0))],
        op("and", v("a"), op("or", v("b"), v("c"))), 0))
    return result


def validity_instance(mask: int):
    names = ["u0", "u1"]
    return model(f"validity-{mask:02d}", [inp(x) for x in names], [],
                 [wire("c", 1, c(1, 0))],
                 op("and", v("c"), truth_table(mask, names)), 0)


def minimality_instance(phi: int, psi: int):
    return model(f"minimality-{phi}-{psi}", [inp("x"), inp("y")], [],
                 [wire("c", 1, c(1, 0)), wire("r", 1, c(1, 0))],
                 op("or", op("and", v("c"), truth_table(phi, ["x"])),
                    op("and", v("r"), truth_table(psi, ["y"]))), 0)


def choice_instance(n: int, universals: int, mask: int):
    us = ["u" + str(i) for i in range(universals)]
    a = ["a" + str(i) for i in range(n)]
    b = ["b" + str(i) for i in range(n)]
    wires = [wire(name, 1, c(1, 0)) for pair in zip(a, b) for name in pair]
    pair_bad = combine("or", [op("and", v(x), v(y)) for x, y in zip(a, b)], 0)
    active = combine("and", [op("xor", v(x), v(y)) for x, y in zip(a, b)], 1)
    formula = truth_table(mask, a + us)
    done = op("or", pair_bad, op("and", active, op("not", formula)))
    return model(f"choice-{n}-{universals}-{mask:03d}", [inp(x) for x in us], [], wires, done, 0)


def wider_masks():
    # Arithmetic selection fixed before running any reduction instances.
    return sorted({0, 255} | {(73 * i + 19) % 256 for i in range(30)})


def reductions():
    result = []
    for mask in range(16):
        result.append((validity_instance(mask), {"family": "validity", "mask": mask}))
    for phi in range(4):
        for psi in range(4):
            result.append((minimality_instance(phi, psi),
                           {"family": "minimality", "phi": phi, "psi": psi}))
    for n, u, masks in [(1, 1, range(16)), (2, 0, range(16)), (2, 1, wider_masks())]:
        for mask in masks:
            result.append((choice_instance(n, u, mask),
                           {"family": "choice", "n": n, "universals": u, "mask": mask}))
    return result


def write_cases(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for item in controls() + [m for m, _ in reductions()]:
        (root / (item["id"] + ".json")).write_text(json.dumps(item, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    write_cases(Path(__file__).resolve().parents[1] / "cases")
