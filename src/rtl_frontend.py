"""Restricted single-clock Verilog-to-equation translator.

This is deliberately not a SystemVerilog frontend.  It accepts only the
source fragment documented in ``rtl-subset.md`` and exercised by the pinned
public suite: scalar/vector ports and registers, constant/identifier
expressions, unary ``- ! ~``, selected binary operators, ternaries,
synchronous ``always @(posedge clock)`` blocks, nested ``if/else``, simple
priority ``case`` statements, ``begin/end`` blocks, nonblocking assignments,
constant initial assignments, and acyclic continuous assignments.  Assertions
and assumptions are outside the translated transition relation and are skipped
only as complete statements.

The independent translation checker in ``rtl_translation_checker.py`` does not
import this module and reconstructs the accepted source semantics separately.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any


class FrontendError(ValueError):
    pass


@dataclass(frozen=True)
class Expr:
    op: str
    args: tuple[Any, ...]


@dataclass
class Signal:
    name: str
    width: int
    direction: str | None = None
    is_reg: bool = False
    init: int | None = None


@dataclass
class Assignment:
    target: str
    guard: Expr
    value: Expr


@dataclass
class Continuous:
    target: str
    value: Expr


@dataclass
class Module:
    name: str
    signals: dict[str, Signal]
    clocks: set[str]
    assignments: list[Assignment]
    continuous: list[Continuous]


_TOKEN_RE = re.compile(
    r"\s*(?:(\d+'[bBoOdDhH][0-9a-fA-F_xXzZ]+)|(\d+)|([A-Za-z_$][A-Za-z0-9_$]*)|"
    r"(<=|==|!=|&&|\|\||>=|<<|>>|[()\[\]{},;:@?'~!+\-*/%&|^<>:=]))"
)
_IDENT_RE = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")
_NUM_RE = re.compile(r"\d+(?:'[bBoOdDhH][0-9a-fA-F_xXzZ]+)?")


def strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    text = re.sub(r"//[^\n]*", " ", text)
    # Yosys examples occasionally place whitespace inside sized literals.
    return re.sub(r"(\d+)\s*'\s*([bBoOdDhH])\s*([0-9a-fA-F_xXzZ]+)", r"\1'\2\3", text)


def tokenize(text: str) -> list[str]:
    text = strip_comments(text)
    out: list[str] = []
    pos = 0
    while pos < len(text):
        m = _TOKEN_RE.match(text, pos)
        if not m:
            if text[pos:].strip() == "":
                break
            raise FrontendError(f"unsupported token near {text[pos:pos+40]!r}")
        out.append(next(x for x in m.groups() if x is not None))
        pos = m.end()
    return out


class Stream:
    def __init__(self, tokens: list[str]):
        self.tokens = tokens
        self.i = 0

    def peek(self, offset: int = 0) -> str | None:
        j = self.i + offset
        return self.tokens[j] if j < len(self.tokens) else None

    def pop(self, expected: str | None = None) -> str:
        if self.i >= len(self.tokens):
            raise FrontendError("unexpected end of input")
        value = self.tokens[self.i]
        if expected is not None and value != expected:
            raise FrontendError(f"expected {expected!r}, got {value!r}")
        self.i += 1
        return value

    def accept(self, value: str) -> bool:
        if self.peek() == value:
            self.i += 1
            return True
        return False

    def skip_to(self, value: str) -> None:
        while self.peek() is not None and self.pop() != value:
            pass


_PRECEDENCE = {
    "||": 1,
    "&&": 2,
    "|": 3,
    "^": 4,
    "&": 5,
    "==": 6,
    "!=": 6,
    "<": 7,
    ">": 7,
    "+": 8,
    "-": 8,
}


def parse_number(token: str) -> Expr:
    if "'" not in token:
        return Expr("const", (None, int(token, 10)))
    width_s, rest = token.split("'", 1)
    base_code, digits = rest[0].lower(), rest[1:].replace("_", "")
    if any(ch.lower() in "xz" for ch in digits):
        raise FrontendError("four-state literals are outside the pilot subset")
    base = {"b": 2, "o": 8, "d": 10, "h": 16}[base_code]
    return Expr("const", (int(width_s), int(digits, base)))


def parse_expr(stream: Stream, min_prec: int = 0) -> Expr:
    token = stream.pop()
    if token == "(":
        lhs = parse_expr(stream)
        stream.pop(")")
    elif token in ("-", "!", "~"):
        lhs = Expr({"-": "neg", "!": "lnot", "~": "bnot"}[token],
                   (parse_expr(stream, 9),))
    elif _NUM_RE.fullmatch(token):
        lhs = parse_number(token)
    elif _IDENT_RE.fullmatch(token):
        lhs = Expr("var", (token,))
    else:
        raise FrontendError(f"expression atom {token!r}")

    while True:
        op = stream.peek()
        if op == "?" and min_prec <= 0:
            stream.pop("?")
            yes = parse_expr(stream)
            stream.pop(":")
            no = parse_expr(stream)
            lhs = Expr("mux", (lhs, yes, no))
            continue
        prec = _PRECEDENCE.get(op or "")
        if prec is None or prec < min_prec:
            break
        stream.pop()
        rhs = parse_expr(stream, prec + 1)
        lhs = Expr(op, (lhs, rhs))
    return lhs


def expr_and(a: Expr, b: Expr) -> Expr:
    return Expr("&&", (a, b))


def expr_or(a: Expr, b: Expr) -> Expr:
    return Expr("||", (a, b))


def expr_not(a: Expr) -> Expr:
    return Expr("lnot", (a,))


def expr_eq(a: Expr, b: Expr) -> Expr:
    return Expr("==", (a, b))


def parse_range(stream: Stream) -> int:
    if not stream.accept("["):
        return 1
    msb = stream.pop()
    stream.pop(":")
    lsb = stream.pop()
    stream.pop("]")
    if not msb.isdigit() or not lsb.isdigit() or int(lsb) != 0:
        raise FrontendError("only literal [msb:0] ranges are supported")
    return int(msb) + 1


def declare(signals: dict[str, Signal], name: str, width: int,
            direction: str | None, is_reg: bool) -> None:
    if not _IDENT_RE.fullmatch(name):
        raise FrontendError(f"invalid signal name {name!r}")
    if name in signals:
        old = signals[name]
        if old.width != width and old.width != 1:
            raise FrontendError(f"conflicting width for {name}")
        old.width = width
        old.direction = direction or old.direction
        old.is_reg = old.is_reg or is_reg
    else:
        signals[name] = Signal(name, width, direction, is_reg)


def parse_header_ports(stream: Stream, signals: dict[str, Signal]) -> None:
    direction: str | None = None
    is_reg = False
    width = 1
    while stream.peek() != ")":
        tok = stream.peek()
        if tok in ("input", "output"):
            direction = stream.pop()
            is_reg = stream.accept("reg")
            stream.accept("wire")
            width = parse_range(stream)
        elif tok == ",":
            stream.pop()
        else:
            name = stream.pop()
            if not _IDENT_RE.fullmatch(name):
                raise FrontendError("malformed module port")
            if direction is not None:
                declare(signals, name, width, direction, is_reg)
            else:
                declare(signals, name, 1, None, False)
    stream.pop(")")


def parse_declaration(stream: Stream, signals: dict[str, Signal]) -> None:
    kind = stream.pop()
    direction = kind if kind in ("input", "output") else None
    is_reg = kind == "reg" or stream.accept("reg")
    stream.accept("wire")
    width = parse_range(stream)
    while True:
        name = stream.pop()
        declare(signals, name, width, direction, is_reg)
        if stream.accept("="):
            e = parse_expr(stream)
            if e.op != "const":
                raise FrontendError("only constant declaration initializers are supported")
            signals[name].init = int(e.args[1])
        if stream.accept(","):
            continue
        stream.pop(";")
        return


def parse_case(stream: Stream, guard: Expr, out: list[Assignment]) -> None:
    stream.pop("case")
    stream.pop("(")
    selector = parse_expr(stream)
    stream.pop(")")
    prior = Expr("const", (1, 0))
    saw_default = False
    default_match = None
    default_updates: list[Assignment] = []
    while stream.peek() != "endcase":
        if stream.accept("default"):
            if saw_default:
                raise FrontendError("duplicate default case")
            saw_default = True
            match = expr_not(prior)
            default_match = match
        else:
            labels = [parse_expr(stream)]
            while stream.accept(","):
                labels.append(parse_expr(stream))
            raw_match = expr_eq(selector, labels[0])
            for label in labels[1:]:
                raw_match = expr_or(raw_match, expr_eq(selector, label))
            match = expr_and(raw_match, expr_not(prior))
            prior = expr_or(prior, raw_match)
        stream.pop(":")
        before = len(out)
        parse_statement(stream, expr_and(guard, match), out)
        if match is default_match:
            default_updates.extend(out[before:])
    stream.pop("endcase")
    # A default is selected only if *all* explicit labels fail, independent of
    # its textual position. Bind it after collecting the complete label set.
    def bind_default(expr: Expr) -> Expr:
        if expr is default_match:
            return expr_not(prior)
        return Expr(expr.op, tuple(bind_default(a) if isinstance(a, Expr) else a
                                  for a in expr.args))
    for assignment in default_updates:
        assignment.guard = bind_default(assignment.guard)


def parse_statement(stream: Stream, guard: Expr, out: list[Assignment]) -> None:
    tok = stream.peek()
    if tok == "begin":
        stream.pop()
        if stream.accept(":"):
            label = stream.pop()
            if not _IDENT_RE.fullmatch(label):
                raise FrontendError("invalid named block")
        while stream.peek() != "end":
            parse_statement(stream, guard, out)
        stream.pop("end")
        return
    if tok == "if":
        stream.pop()
        stream.pop("(")
        cond = parse_expr(stream)
        stream.pop(")")
        parse_statement(stream, expr_and(guard, cond), out)
        if stream.accept("else"):
            parse_statement(stream, expr_and(guard, expr_not(cond)), out)
        return
    if tok == "case":
        parse_case(stream, guard, out)
        return
    if tok in ("assert", "assume", "cover"):
        stream.skip_to(";")
        return
    if tok == ";":
        stream.pop()
        return
    target = stream.pop()
    if not _IDENT_RE.fullmatch(target):
        raise FrontendError(f"unsupported statement starting at {target!r}")
    stream.pop("<=")
    value = parse_expr(stream)
    stream.pop(";")
    out.append(Assignment(target, guard, value))


def _target_tokens(text: str, module_name: str) -> list[str]:
    tokens = tokenize(text)
    for i in range(len(tokens) - 1):
        if tokens[i] == "module" and tokens[i + 1] == module_name:
            for j in range(i + 2, len(tokens)):
                if tokens[j] == "endmodule":
                    return tokens[i:j + 1]
            raise FrontendError(f"unterminated module {module_name!r}")
    raise FrontendError(f"module {module_name!r} not found")


def parse_module(text: str, module_name: str) -> Module:
    stream = Stream(_target_tokens(text, module_name))
    stream.pop("module")
    name = stream.pop()
    if name != module_name:
        raise FrontendError("target-module extraction failure")
    signals: dict[str, Signal] = {}
    if stream.accept("("):
        parse_header_ports(stream, signals)
    stream.pop(";")
    clocks: set[str] = set()
    assignments: list[Assignment] = []
    continuous: list[Continuous] = []
    procedural_drivers: set[str] = set()
    while stream.peek() != "endmodule":
        tok = stream.peek()
        if tok in ("input", "output", "reg", "wire"):
            parse_declaration(stream, signals)
        elif tok == "initial":
            stream.pop()
            target = stream.pop()
            stream.pop("=")
            e = parse_expr(stream)
            stream.pop(";")
            if target not in signals or e.op != "const":
                raise FrontendError("unsupported initial assignment")
            signals[target].init = int(e.args[1])
        elif tok == "assign":
            stream.pop()
            target = stream.pop()
            if not _IDENT_RE.fullmatch(target):
                raise FrontendError("indexed continuous assignment is outside the subset")
            stream.pop("=")
            value = parse_expr(stream)
            stream.pop(";")
            continuous.append(Continuous(target, value))
        elif tok == "always":
            stream.pop()
            stream.pop("@")
            stream.pop("(")
            stream.pop("posedge")
            clock = stream.pop()
            stream.pop(")")
            clocks.add(clock)
            before = len(assignments)
            parse_statement(stream, Expr("const", (1, 1)), assignments)
            driven_here = {item.target for item in assignments[before:]}
            if procedural_drivers & driven_here:
                raise FrontendError("multiple procedural blocks drive the same register")
            procedural_drivers |= driven_here
        elif tok in ("assert", "assume", "cover"):
            stream.skip_to(";")
        else:
            raise FrontendError(f"unsupported module item {tok!r} in {name}")
    stream.pop("endmodule")
    if stream.peek() is not None:
        raise FrontendError("tokens after target endmodule")
    return Module(name, signals, clocks, assignments, continuous)


def const(width: int, value: int) -> list:
    return ["const", width, value & ((1 << width) - 1)]


def var(name: str) -> list:
    return ["var", name]


def _bool(ir: list, width: int) -> list:
    return ir if width == 1 else ["not", ["eq", ir, const(width, 0)]]


def compile_expr(e: Expr, widths: dict[str, int], expected: int | None = None) -> tuple[list, int]:
    if e.op == "var":
        name = e.args[0]
        if name not in widths:
            raise FrontendError(f"unknown identifier {name}")
        return var(name), widths[name]
    if e.op == "const":
        width, value = e.args
        if width is None and expected is not None and not 0 <= int(value) < (1 << expected):
            raise FrontendError("unsized literal does not fit the supported context width")
        width = expected if width is None else width
        if width is None:
            width = max(1, int(value).bit_length())
        return const(width, int(value)), width
    if e.op in ("neg", "bnot", "lnot"):
        a, aw = compile_expr(e.args[0], widths, None if e.op == "lnot" else expected)
        if e.op == "neg":
            return ["sub", const(aw, 0), a], aw
        if e.op == "bnot":
            return ["not", a], aw
        return ["not", _bool(a, aw)], 1
    if e.op == "mux":
        c_ir, cw = compile_expr(e.args[0], widths)
        left, right = e.args[1], e.args[2]
        inferred = expected
        if inferred is None and left.op != "const":
            _, inferred = compile_expr(left, widths)
        if inferred is None and right.op != "const":
            _, inferred = compile_expr(right, widths)
        y_ir, yw = compile_expr(left, widths, inferred)
        n_ir, nw = compile_expr(right, widths, yw)
        if yw != nw:
            raise FrontendError("ternary branch width mismatch")
        return ["mux", _bool(c_ir, cw), y_ir, n_ir], yw

    a, b = e.args
    if e.op in ("&&", "||"):
        a_ir, aw = compile_expr(a, widths)
        b_ir, bw = compile_expr(b, widths)
        return (["and" if e.op == "&&" else "or", _bool(a_ir, aw), _bool(b_ir, bw)], 1)
    if a.op == "const" and a.args[0] is None and b.op != "const":
        b_ir, bw = compile_expr(b, widths)
        a_ir, aw = compile_expr(a, widths, bw)
    elif b.op == "const" and b.args[0] is None and a.op != "const":
        a_ir, aw = compile_expr(a, widths)
        b_ir, bw = compile_expr(b, widths, aw)
    else:
        a_ir, aw = compile_expr(a, widths, expected)
        b_ir, bw = compile_expr(b, widths,
                                aw if b.op == "const" and b.args[0] is None else expected)
    op = e.op
    if aw != bw:
        raise FrontendError(f"operand width mismatch for {op}: {aw} vs {bw}")
    if op == "+":
        return ["add", a_ir, b_ir], aw
    if op == "-":
        return ["sub", a_ir, b_ir], aw
    if op == "&":
        return ["and", a_ir, b_ir], aw
    if op == "|":
        return ["or", a_ir, b_ir], aw
    if op == "^":
        return ["xor", a_ir, b_ir], aw
    if op == "==":
        return ["eq", a_ir, b_ir], 1
    if op == "!=":
        return ["not", ["eq", a_ir, b_ir]], 1
    if op == "<":
        return ["ult", a_ir, b_ir], 1
    if op == ">":
        return ["ult", b_ir, a_ir], 1
    raise FrontendError(f"unsupported expression operator {op}")


def input_domains(spec: dict[str, list[int]], signals: dict[str, Signal], clock: str) -> list[dict]:
    result = []
    for name, signal in signals.items():
        if signal.direction != "input" or name == clock:
            continue
        values = spec.get(name)
        if values is None:
            if signal.width > 4:
                raise FrontendError(f"explicit finite domain required for input {name}")
            values = list(range(1 << signal.width))
        if not values or sorted(set(values)) != values:
            raise FrontendError(f"invalid domain for {name}")
        if any(v < 0 or v >= (1 << signal.width) for v in values):
            raise FrontendError(f"input value out of range for {name}")
        result.append({"name": name, "width": signal.width, "values": values})
    unknown = set(spec) - {d["name"] for d in result}
    if unknown:
        raise FrontendError(f"domains for non-inputs: {sorted(unknown)}")
    return result


def translate(text: str, *, module_name: str, model_id: str, clock: str,
              done_expression: str, horizon: int, domains: dict[str, list[int]],
              initial_state: dict[str, int], cuttable: set[str]) -> tuple[dict, Module]:
    module = parse_module(text, module_name)
    if module.clocks != {clock}:
        raise FrontendError(f"expected exactly clock {clock}, saw {sorted(module.clocks)}")
    widths = {name: signal.width for name, signal in module.signals.items()}
    assigned = {a.target for a in module.assignments}
    continuous_targets = {a.target for a in module.continuous}
    if len(continuous_targets) != len(module.continuous):
        raise FrontendError("multiple continuous assignments to one target")
    if assigned & continuous_targets:
        raise FrontendError("signal has both procedural and continuous assignment")
    for target in assigned:
        if target not in module.signals:
            raise FrontendError(f"assignment to undeclared {target}")
        module.signals[target].is_reg = True
    for target in continuous_targets:
        if target not in module.signals:
            raise FrontendError(f"continuous assignment to undeclared {target}")
        if module.signals[target].is_reg:
            raise FrontendError(f"continuous assignment to register {target}")

    inputs = input_domains(domains, module.signals, clock)
    wires = []
    for item in module.continuous:
        width = module.signals[item.target].width
        expr_ir, ew = compile_expr(item.value, widths, width)
        if ew != width:
            raise FrontendError(f"continuous assignment width mismatch for {item.target}")
        wires.append({"name": item.target, "width": width, "expr": expr_ir, "cut": False})

    registers = []
    for name in sorted(assigned):
        signal = module.signals[name]
        current: list = var(name)
        for item in module.assignments:
            if item.target != name:
                continue
            guard_ir, gw = compile_expr(item.guard, widths)
            rhs_ir, rw = compile_expr(item.value, widths, signal.width)
            if rw != signal.width:
                raise FrontendError(f"assignment width mismatch for {name}")
            # Later nonblocking assignments win when guards overlap.
            current = ["mux", _bool(guard_ir, gw), rhs_ir, current]
        init = initial_state.get(name, signal.init if signal.init is not None else 0)
        if not 0 <= init < (1 << signal.width):
            raise FrontendError(f"initial value out of range for {name}")
        registers.append({"name": name, "width": signal.width, "init": init,
                          "next": current, "cut": name in cuttable})
    if set(initial_state) - assigned:
        raise FrontendError("initial-state override for non-register")
    if cuttable - assigned:
        raise FrontendError("cuttable name is not a procedural register")

    done_tokens = Stream(tokenize(done_expression))
    done_ast = parse_expr(done_tokens)
    if done_tokens.peek() is not None:
        raise FrontendError("trailing tokens in completion expression")
    done_ir, dw = compile_expr(done_ast, widths, 1)
    if dw != 1:
        raise FrontendError("completion expression is not Boolean")
    raw = {"id": model_id, "inputs": inputs, "registers": registers, "wires": wires,
           "done": done_ir, "horizon": horizon}
    return raw, module


def eval_expr(e: Expr, env: dict[str, int], widths: dict[str, int],
              expected: int | None = None) -> tuple[int, int]:
    """AST evaluator retained only for parser-level diagnostic probes."""
    ir, width = compile_expr(e, widths, expected)
    from .producer import evaluate, parse
    return evaluate(parse(ir, widths), env), width
