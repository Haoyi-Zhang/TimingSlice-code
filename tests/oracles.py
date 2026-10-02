"""Closed-form, non-IR oracles for the fixed scientific pilot.

No producer/checker imports. These functions do not certify arbitrary models;
they provide independent exact answers for the stated finite fixtures.
"""
from __future__ import annotations

import itertools


def scalar(mask: int, bits: tuple[int, ...]) -> int:
    index = 0
    for bit in bits: index = 2 * index + bit
    return (mask >> index) & 1


def reduction_done(meta: dict, u: tuple, cut: dict) -> int:
    f = meta["family"]
    if f == "validity":
        return cut.get("w:c", 0) & scalar(meta["mask"], u)
    if f == "minimality":
        return ((cut.get("w:c", 0) & scalar(meta["phi"], (u[0],))) |
                (cut.get("w:r", 0) & scalar(meta["psi"], (u[1],))))
    a = tuple(cut.get("w:a" + str(i), 0) for i in range(meta["n"]))
    b = tuple(cut.get("w:b" + str(i), 0) for i in range(meta["n"]))
    if any(x == 1 and y == 1 for x, y in zip(a, b)): return 1
    active = all(x != y for x, y in zip(a, b))
    return int(active and scalar(meta["mask"], a + u) == 0)


def reduction_oracle(meta: dict, domains: list[list[int]], free: list[str]) -> tuple[bool, tuple | None, int]:
    count = 0
    for u in itertools.product(*domains):
        for vals in itertools.product((0, 1), repeat=len(free)):
            count += 1
            if reduction_done(meta, u, dict(zip(free, vals))):
                return False, (u, vals), count
    return True, None, count


def quantified_choice(meta: dict) -> bool:
    for assignment in itertools.product((0, 1), repeat=meta["n"]):
        if all(scalar(meta["mask"], assignment + u)
               for u in itertools.product((0, 1), repeat=meta["universals"])):
            return True
    return False


def hand_step(name: str, state: tuple, u: tuple, cut: dict) -> tuple[int, tuple]:
    def w(n: str, default: int): return cut.get("w:" + n, default)
    def r(n: str, default: int): return cut.get("r:" + n, default)
    if name == "joint-omission": return w("a", 0) & w("b", 0), ()
    if name == "zero-cancellation": return w("a", 1) ^ w("b", 1), ()
    if name == "minimum-gap": return w("a", 0) & (w("b", 0) | w("c", 0)), ()
    if name == "post-completion":
        phase, flag, payload = state
        done = 1 if phase == 2 else int(phase == 3) & (flag ^ (payload & 1))
        return done, (r("phase", min(3, phase + 1)), r("flag", u[0]), r("payload", (payload + 1) % 4))
    if name == "enable-counter":
        (q,) = state
        return int(q == 3), (r("q", (q + 1) % 4 if w("gate", u[0]) else q),)
    if name == "reset-counter":
        (q,) = state
        nq = 0 if w("rst", u[0]) else ((q + 1) % 4 if u[1] else q)
        return int(q == 2), (r("q", nq),)
    if name == "old-value-pipeline":
        a, b = state
        return b, (r("a", u[0]), r("b", a))
    if name == "wrap-counter":
        (q,) = state
        return int(q == 0), (r("q", (q + 1) % 4),)
    if name == "never-complete": return 0, (r("q", state[0] ^ 1),)
    if name == "initial-completion": return state[0], (r("q", u[0]),)
    if name == "wire-width": return int(w("w", (u[0] + 1) % 4) == 0), ()
    if name == "concat-slice":
        joined = w("joined", 2 * u[1] + u[0])
        return w("top", joined // 2), ()
    if name == "shared-wire":
        a = w("a", u[0])
        return a ^ a, ()
    raise ValueError("no hand oracle for this case")


def exhaustive_witness(raw: dict, keep: set[str], mode: str, depth: int) -> tuple[dict | None, int]:
    """Enumerate entire prefixes (no state merging), input-primary order."""
    wc = [("w:" + d["name"], d["width"]) for d in raw["wires"]
          if d["cut"] and "w:" + d["name"] not in keep]
    rc = [("r:" + d["name"], d["width"]) for d in raw["registers"]
          if d["cut"] and "r:" + d["name"] not in keep]
    alphabet = list(itertools.product(*[d["values"] for d in raw["inputs"]]))
    initial = tuple(d["init"] for d in raw["registers"])
    count = 0
    for d in range(depth + 1):
        fields = [wc + (rc if t < d else []) for t in range(d + 1)]
        alphabets = [list(itertools.product(*[range(1 << width) for _, width in f])) for f in fields]
        for us in itertools.product(alphabet, repeat=d + 1):
            for cs in itertools.product(*alphabets):
                s = a = initial
                cuts = [dict(zip([key for key, _ in f], vals)) for f, vals in zip(fields, cs)]
                for t in range(d + 1):
                    count += 1
                    ds, ns = hand_step(raw["id"], s, us[t], {})
                    da, na = hand_step(raw["id"], a, us[t], cuts[t])
                    if ds != da:
                        if t == d:
                            return {"time": d, "inputs": [list(x) for x in us], "cuts": cuts}, count
                        break
                    if mode == "first-hit" and ds: break
                    s, a = ns, na
    return None, count
