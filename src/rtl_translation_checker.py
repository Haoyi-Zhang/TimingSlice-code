"""Independent checker for the restricted RTL-to-equation translation.

The checker intentionally imports neither ``rtl_frontend`` nor the proof-bundle
producer/checker.  It has a separate lexer, parser, source-semantics compiler,
and equation-IR validator.  Acceptance establishes exact structural semantic
correspondence for the documented source fragment, plus source-blob, harness,
initial-state, domain, horizon, and cut-policy binding.  It is not a verifier for
unrestricted Verilog/SystemVerilog and its own parser remains trusted code.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from typing import Any


class TranslationValidationError(ValueError):
    pass


@dataclass(frozen=True)
class VExpr:
    tag: str
    children: tuple[Any, ...]


@dataclass
class VSignal:
    width: int
    direction: str | None
    register: bool
    initial: int | None = None


@dataclass
class VUpdate:
    target: str
    condition: VExpr
    value: VExpr


@dataclass
class VModule:
    signals: dict[str, VSignal]
    clocks: set[str]
    updates: list[VUpdate]
    continuous: list[tuple[str, VExpr]]


_LEX = re.compile(
    r"\s*(?:(\d+'[bBoOdDhH][0-9a-fA-F_xXzZ]+)|(\d+)|([A-Za-z_$][A-Za-z0-9_$]*)|"
    r"(<=|==|!=|&&|\|\||>=|<<|>>|[()\[\]{},;:@?'~!+\-*/%&|^<>:=]))"
)
_IDENTIFIER = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")
_NUMBER = re.compile(r"\d+(?:'[bBoOdDhH][0-9a-fA-F_xXzZ]+)?")
_ORDER = {"||": 1, "&&": 2, "|": 3, "^": 4, "&": 5,
          "==": 6, "!=": 6, "<": 7, ">": 7, "+": 8, "-": 8}


def _without_comments(source: str) -> str:
    source = re.sub(r"/\*.*?\*/", " ", source, flags=re.S)
    source = re.sub(r"//[^\n]*", " ", source)
    return re.sub(r"(\d+)\s*'\s*([bBoOdDhH])\s*([0-9a-fA-F_xXzZ]+)",
                  r"\1'\2\3", source)


def _tokens(source: str) -> list[str]:
    source = _without_comments(source)
    result: list[str] = []
    position = 0
    while position < len(source):
        match = _LEX.match(source, position)
        if match is None:
            if not source[position:].strip():
                break
            raise TranslationValidationError(
                f"independent lexer rejected {source[position:position+32]!r}")
        result.append(next(part for part in match.groups() if part is not None))
        position = match.end()
    return result


class Cursor:
    def __init__(self, items: list[str]):
        self.items = items
        self.position = 0

    def look(self, offset: int = 0) -> str | None:
        index = self.position + offset
        return self.items[index] if index < len(self.items) else None

    def take(self, required: str | None = None) -> str:
        if self.position >= len(self.items):
            raise TranslationValidationError("unexpected end of source")
        item = self.items[self.position]
        if required is not None and item != required:
            raise TranslationValidationError(f"expected {required!r}, found {item!r}")
        self.position += 1
        return item

    def maybe(self, item: str) -> bool:
        if self.look() == item:
            self.position += 1
            return True
        return False

    def discard_through(self, item: str) -> None:
        while self.look() is not None:
            if self.take() == item:
                return
        raise TranslationValidationError(f"unterminated statement looking for {item!r}")


def _literal(token: str) -> VExpr:
    if "'" not in token:
        return VExpr("constant", (None, int(token)))
    size, payload = token.split("'", 1)
    radix, digits = payload[0].lower(), payload[1:].replace("_", "")
    if any(character.lower() in "xz" for character in digits):
        raise TranslationValidationError("four-state literal")
    value = int(digits, {"b": 2, "o": 8, "d": 10, "h": 16}[radix])
    return VExpr("constant", (int(size), value))


def _expression(cursor: Cursor, minimum: int = 0) -> VExpr:
    token = cursor.take()
    if token == "(":
        left = _expression(cursor)
        cursor.take(")")
    elif token in ("-", "!", "~"):
        left = VExpr({"-": "negative", "!": "logical-not", "~": "bit-not"}[token],
                     (_expression(cursor, 9),))
    elif _NUMBER.fullmatch(token):
        left = _literal(token)
    elif _IDENTIFIER.fullmatch(token):
        left = VExpr("identifier", (token,))
    else:
        raise TranslationValidationError(f"bad expression atom {token!r}")

    while True:
        operator = cursor.look()
        if operator == "?" and minimum <= 0:
            cursor.take("?")
            when_true = _expression(cursor)
            cursor.take(":")
            when_false = _expression(cursor)
            left = VExpr("conditional", (left, when_true, when_false))
            continue
        precedence = _ORDER.get(operator or "")
        if precedence is None or precedence < minimum:
            return left
        cursor.take()
        right = _expression(cursor, precedence + 1)
        left = VExpr(operator, (left, right))


def _and(left: VExpr, right: VExpr) -> VExpr:
    return VExpr("&&", (left, right))


def _or(left: VExpr, right: VExpr) -> VExpr:
    return VExpr("||", (left, right))


def _not(value: VExpr) -> VExpr:
    return VExpr("logical-not", (value,))


def _equal(left: VExpr, right: VExpr) -> VExpr:
    return VExpr("==", (left, right))


def _width(cursor: Cursor) -> int:
    if not cursor.maybe("["):
        return 1
    upper = cursor.take()
    cursor.take(":")
    lower = cursor.take()
    cursor.take("]")
    if not upper.isdigit() or lower != "0":
        raise TranslationValidationError("independent parser accepts only [literal:0]")
    return int(upper) + 1


def _record_signal(signals: dict[str, VSignal], name: str, width: int,
                   direction: str | None, register: bool) -> None:
    if not _IDENTIFIER.fullmatch(name):
        raise TranslationValidationError("invalid signal name")
    existing = signals.get(name)
    if existing is None:
        signals[name] = VSignal(width, direction, register)
        return
    if existing.width not in (1, width) and width != 1:
        raise TranslationValidationError(f"width conflict for {name}")
    existing.width = width
    existing.direction = direction or existing.direction
    existing.register = existing.register or register


def _ports(cursor: Cursor, signals: dict[str, VSignal]) -> None:
    direction: str | None = None
    register = False
    width = 1
    while cursor.look() != ")":
        if cursor.look() in ("input", "output"):
            direction = cursor.take()
            register = cursor.maybe("reg")
            cursor.maybe("wire")
            width = _width(cursor)
        elif cursor.maybe(","):
            pass
        else:
            name = cursor.take()
            _record_signal(signals, name, width if direction else 1,
                           direction, register if direction else False)
    cursor.take(")")


def _declaration(cursor: Cursor, signals: dict[str, VSignal]) -> None:
    kind = cursor.take()
    direction = kind if kind in ("input", "output") else None
    register = kind == "reg" or cursor.maybe("reg")
    cursor.maybe("wire")
    width = _width(cursor)
    while True:
        name = cursor.take()
        _record_signal(signals, name, width, direction, register)
        if cursor.maybe("="):
            value = _expression(cursor)
            if value.tag != "constant":
                raise TranslationValidationError("nonconstant declaration initializer")
            signals[name].initial = int(value.children[1])
        if not cursor.maybe(","):
            cursor.take(";")
            return


def _case(cursor: Cursor, outer: VExpr, updates: list[VUpdate]) -> None:
    cursor.take("case")
    cursor.take("(")
    selector = _expression(cursor)
    cursor.take(")")
    previous = VExpr("constant", (1, 0))
    default_seen = False
    default_condition = None
    fallback_updates: list[VUpdate] = []
    while cursor.look() != "endcase":
        if cursor.maybe("default"):
            if default_seen:
                raise TranslationValidationError("duplicate default")
            default_seen = True
            active = _not(previous)
            default_condition = active
        else:
            labels = [_expression(cursor)]
            while cursor.maybe(","):
                labels.append(_expression(cursor))
            raw = _equal(selector, labels[0])
            for label in labels[1:]:
                raw = _or(raw, _equal(selector, label))
            active = _and(raw, _not(previous))
            previous = _or(previous, raw)
        cursor.take(":")
        start = len(updates)
        _statement(cursor, _and(outer, active), updates)
        if active is default_condition:
            fallback_updates.extend(updates[start:])
    cursor.take("endcase")
    # Default means no explicit item matches, even if it precedes an item.
    def complete_fallback(node: VExpr) -> VExpr:
        if node is default_condition:
            return _not(previous)
        children = tuple(complete_fallback(child) if isinstance(child, VExpr) else child
                         for child in node.children)
        return VExpr(node.tag, children)
    for update in fallback_updates:
        update.condition = complete_fallback(update.condition)


def _statement(cursor: Cursor, condition: VExpr, updates: list[VUpdate]) -> None:
    token = cursor.look()
    if token == "begin":
        cursor.take()
        if cursor.maybe(":"):
            cursor.take()
        while cursor.look() != "end":
            _statement(cursor, condition, updates)
        cursor.take("end")
        return
    if token == "if":
        cursor.take()
        cursor.take("(")
        predicate = _expression(cursor)
        cursor.take(")")
        _statement(cursor, _and(condition, predicate), updates)
        if cursor.maybe("else"):
            _statement(cursor, _and(condition, _not(predicate)), updates)
        return
    if token == "case":
        _case(cursor, condition, updates)
        return
    if token in ("assert", "assume", "cover"):
        cursor.discard_through(";")
        return
    if token == ";":
        cursor.take()
        return
    target = cursor.take()
    if not _IDENTIFIER.fullmatch(target):
        raise TranslationValidationError("unsupported procedural target")
    cursor.take("<=")
    value = _expression(cursor)
    cursor.take(";")
    updates.append(VUpdate(target, condition, value))


def _target_module_tokens(source: str, module_name: str) -> list[str]:
    tokens = _tokens(source)
    for index in range(len(tokens) - 1):
        if tokens[index] == "module" and tokens[index + 1] == module_name:
            try:
                end = tokens.index("endmodule", index + 2)
            except ValueError as exc:
                raise TranslationValidationError("unterminated target module") from exc
            return tokens[index:end + 1]
    raise TranslationValidationError("target module absent")


def _parse_source(source: str, module_name: str) -> VModule:
    cursor = Cursor(_target_module_tokens(source, module_name))
    cursor.take("module")
    cursor.take(module_name)
    signals: dict[str, VSignal] = {}
    if cursor.maybe("("):
        _ports(cursor, signals)
    cursor.take(";")
    clocks: set[str] = set()
    updates: list[VUpdate] = []
    continuous: list[tuple[str, VExpr]] = []
    block_targets: set[str] = set()
    while cursor.look() != "endmodule":
        item = cursor.look()
        if item in ("input", "output", "reg", "wire"):
            _declaration(cursor, signals)
        elif item == "initial":
            cursor.take()
            target = cursor.take()
            cursor.take("=")
            value = _expression(cursor)
            cursor.take(";")
            if target not in signals or value.tag != "constant":
                raise TranslationValidationError("unsupported initial assignment")
            signals[target].initial = int(value.children[1])
        elif item == "assign":
            cursor.take()
            target = cursor.take()
            cursor.take("=")
            continuous.append((target, _expression(cursor)))
            cursor.take(";")
        elif item == "always":
            cursor.take()
            cursor.take("@")
            cursor.take("(")
            cursor.take("posedge")
            clocks.add(cursor.take())
            cursor.take(")")
            start = len(updates)
            _statement(cursor, VExpr("constant", (1, 1)), updates)
            new_targets = {update.target for update in updates[start:]}
            if not block_targets.isdisjoint(new_targets):
                raise TranslationValidationError("register has more than one procedural driver")
            block_targets.update(new_targets)
        elif item in ("assert", "assume", "cover"):
            cursor.discard_through(";")
        else:
            raise TranslationValidationError(f"unsupported source item {item!r}")
    cursor.take("endmodule")
    if cursor.look() is not None:
        raise TranslationValidationError("trailing target-module tokens")
    return VModule(signals, clocks, updates, continuous)


def _constant(width: int, value: int) -> tuple:
    return ("const", width, value & ((1 << width) - 1))


def _variable(name: str) -> tuple:
    return ("var", name)


def _as_boolean(node: tuple, width: int) -> tuple:
    return node if width == 1 else ("not", ("eq", node, _constant(width, 0)))


def _compile_source(expression: VExpr, widths: dict[str, int],
                    expected: int | None = None) -> tuple[tuple, int, int]:
    """Return canonical node, width, and number of compared expression nodes."""
    tag = expression.tag
    if tag == "identifier":
        name = expression.children[0]
        if name not in widths:
            raise TranslationValidationError(f"unknown source identifier {name}")
        return _variable(name), widths[name], 1
    if tag == "constant":
        width, value = expression.children
        width = expected if width is None else width
        if width is None:
            width = max(1, int(value).bit_length())
        return _constant(width, int(value)), width, 1
    if tag in ("negative", "bit-not", "logical-not"):
        child, child_width, nodes = _compile_source(expression.children[0], widths, expected)
        if tag == "negative":
            return ("sub", _constant(child_width, 0), child), child_width, nodes + 2
        if tag == "bit-not":
            return ("not", child), child_width, nodes + 1
        return ("not", _as_boolean(child, child_width)), 1, nodes + 1
    if tag == "conditional":
        condition, condition_width, cn = _compile_source(expression.children[0], widths)
        left, right = expression.children[1], expression.children[2]
        inferred = expected
        if inferred is None and left.tag != "constant":
            _, inferred, _ = _compile_source(left, widths)
        if inferred is None and right.tag != "constant":
            _, inferred, _ = _compile_source(right, widths)
        yes, yes_width, yn = _compile_source(left, widths, inferred)
        no, no_width, nn = _compile_source(right, widths, yes_width)
        if yes_width != no_width:
            raise TranslationValidationError("source conditional width mismatch")
        return ("mux", _as_boolean(condition, condition_width), yes, no), yes_width, cn + yn + nn + 1

    left_expression, right_expression = expression.children
    if left_expression.tag == "constant" and left_expression.children[0] is None and right_expression.tag != "constant":
        right, right_width, rn = _compile_source(right_expression, widths)
        left, left_width, ln = _compile_source(left_expression, widths, right_width)
    elif right_expression.tag == "constant" and right_expression.children[0] is None and left_expression.tag != "constant":
        left, left_width, ln = _compile_source(left_expression, widths)
        right, right_width, rn = _compile_source(right_expression, widths, left_width)
    else:
        left, left_width, ln = _compile_source(left_expression, widths, expected)
        right_expected = left_width if right_expression.tag == "constant" and right_expression.children[0] is None else expected
        right, right_width, rn = _compile_source(right_expression, widths, right_expected)
    if tag in ("&&", "||"):
        op = "and" if tag == "&&" else "or"
        return (op, _as_boolean(left, left_width), _as_boolean(right, right_width)), 1, ln + rn + 1
    if left_width != right_width:
        raise TranslationValidationError(f"source operand widths disagree for {tag}")
    mapping = {"+": "add", "-": "sub", "&": "and", "|": "or", "^": "xor"}
    if tag in mapping:
        return (mapping[tag], left, right), left_width, ln + rn + 1
    if tag == "==":
        return ("eq", left, right), 1, ln + rn + 1
    if tag == "!=":
        return ("not", ("eq", left, right)), 1, ln + rn + 2
    if tag == "<":
        return ("ult", left, right), 1, ln + rn + 1
    if tag == ">":
        return ("ult", right, left), 1, ln + rn + 1
    raise TranslationValidationError(f"unsupported source operator {tag}")


def _parse_ir(raw: Any, widths: dict[str, int]) -> tuple[tuple, int, int]:
    if not isinstance(raw, list) or not raw or not isinstance(raw[0], str):
        raise TranslationValidationError("malformed equation expression")
    op = raw[0]
    if op == "const":
        if len(raw) != 3 or type(raw[1]) is not int or type(raw[2]) is not int:
            raise TranslationValidationError("malformed constant")
        width = raw[1]
        if not 1 <= width <= 16 or not 0 <= raw[2] < (1 << width):
            raise TranslationValidationError("constant outside declared width")
        return ("const", width, raw[2]), width, 1
    if op == "var":
        if len(raw) != 2 or raw[1] not in widths:
            raise TranslationValidationError("unknown equation variable")
        return ("var", raw[1]), widths[raw[1]], 1
    if op == "not":
        if len(raw) != 2:
            raise TranslationValidationError("malformed not")
        child, width, nodes = _parse_ir(raw[1], widths)
        return ("not", child), width, nodes + 1
    if op == "slice":
        if len(raw) != 4 or type(raw[2]) is not int or type(raw[3]) is not int:
            raise TranslationValidationError("malformed slice")
        child, child_width, nodes = _parse_ir(raw[1], widths)
        low, width = raw[2], raw[3]
        if low < 0 or width < 1 or low + width > child_width:
            raise TranslationValidationError("slice bounds")
        return ("slice", child, low, width), width, nodes + 1
    if op == "mux":
        if len(raw) != 4:
            raise TranslationValidationError("malformed mux")
        condition, cw, cn = _parse_ir(raw[1], widths)
        yes, yw, yn = _parse_ir(raw[2], widths)
        no, nw, nn = _parse_ir(raw[3], widths)
        if cw != 1 or yw != nw:
            raise TranslationValidationError("mux widths")
        return ("mux", condition, yes, no), yw, cn + yn + nn + 1
    if op in ("and", "or", "xor", "add", "sub", "eq", "ult", "concat"):
        if len(raw) != 3:
            raise TranslationValidationError(f"malformed {op}")
        left, lw, ln = _parse_ir(raw[1], widths)
        right, rw, rn = _parse_ir(raw[2], widths)
        if op == "concat":
            width = lw + rw
            if width > 16:
                raise TranslationValidationError("concat width")
        else:
            if lw != rw:
                raise TranslationValidationError(f"{op} operand widths")
            width = 1 if op in ("eq", "ult") else lw
        return (op, left, right), width, ln + rn + 1
    raise TranslationValidationError(f"unknown equation operator {op}")


def _git_blob_sha(source_bytes: bytes) -> str:
    header = f"blob {len(source_bytes)}\0".encode("ascii")
    return hashlib.sha1(header + source_bytes).hexdigest()


def _domains(text: str) -> dict[str, list[int]]:
    if not text:
        return {}
    result: dict[str, list[int]] = {}
    for field in text.split(";"):
        name, payload = field.split("=", 1)
        result[name] = [int(value) for value in payload.split(",")]
    return result


def _initial_state(text: str) -> dict[str, int]:
    if not text:
        return {}
    return {field.split("=", 1)[0]: int(field.split("=", 1)[1])
            for field in text.split(";")}


def _cuttable_policy(text: str) -> set[str]:
    """Parse the manifest-bound candidate set, rejecting ambiguous spellings."""
    if type(text) is not str:
        raise TranslationValidationError("manifest cut policy is not text")
    names = [name.strip() for name in re.split(r"[,;]", text) if name.strip()]
    if len(names) != len(set(names)):
        raise TranslationValidationError("duplicate name in manifest cut policy")
    if any(_IDENTIFIER.fullmatch(name) is None for name in names):
        raise TranslationValidationError("invalid name in manifest cut policy")
    return set(names)


def validate_translation(source_text: str, source_bytes: bytes, manifest: dict[str, str],
                         raw: dict[str, Any], cuttable: set[str]) -> dict[str, Any]:
    if type(source_bytes) is not bytes:
        raise TranslationValidationError("source bytes are not bytes")
    try:
        bound_source_text = source_bytes.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise TranslationValidationError("source bytes are not strict UTF-8") from error
    if source_text != bound_source_text:
        raise TranslationValidationError("source text does not match the pinned source bytes")
    actual_blob = _git_blob_sha(source_bytes)
    if actual_blob != manifest["blob_sha"]:
        raise TranslationValidationError("source blob does not match pinned provenance")
    module = _parse_source(bound_source_text, manifest["module"])
    if module.clocks != {manifest["clock"]}:
        raise TranslationValidationError("clock binding mismatch")
    manifest_cuttable = _cuttable_policy(manifest.get("cuttable", ""))
    if type(cuttable) is not set or cuttable != manifest_cuttable:
        raise TranslationValidationError("external cut policy differs from manifest binding")
    if set(raw) != {"id", "inputs", "registers", "wires", "done", "horizon"}:
        raise TranslationValidationError("model top-level schema")
    if raw["id"] != manifest["case_id"] or raw["horizon"] != int(manifest["horizon"]):
        raise TranslationValidationError("model identity or horizon mismatch")

    widths = {name: signal.width for name, signal in module.signals.items()}
    assigned = {update.target for update in module.updates}
    continuous_targets = [target for target, _ in module.continuous]
    if len(set(continuous_targets)) != len(continuous_targets):
        raise TranslationValidationError("duplicate continuous target")
    if assigned & set(continuous_targets):
        raise TranslationValidationError("mixed procedural/continuous driver")
    for name in assigned:
        if name not in module.signals:
            raise TranslationValidationError("procedural target undeclared")
        module.signals[name].register = True

    expected_domains = _domains(manifest["input_domains"])
    source_inputs = []
    for name, signal in module.signals.items():
        if signal.direction == "input" and name != manifest["clock"]:
            values = expected_domains.get(name)
            if values is None:
                if signal.width > 4:
                    raise TranslationValidationError("wide input lacks explicit finite domain")
                values = list(range(1 << signal.width))
            source_inputs.append({"name": name, "width": signal.width, "values": values})
    if set(expected_domains) != {item["name"] for item in source_inputs}:
        raise TranslationValidationError("input-domain binding mismatch")
    if raw["inputs"] != source_inputs:
        raise TranslationValidationError("translated input declarations differ")

    comparisons = 0
    expected_wires = []
    for target, expression in module.continuous:
        if target not in module.signals or module.signals[target].register:
            raise TranslationValidationError("invalid continuous target")
        node, width, nodes = _compile_source(expression, widths, module.signals[target].width)
        comparisons += nodes
        expected_wires.append((target, module.signals[target].width, node, False))
    if len(raw["wires"]) != len(expected_wires):
        raise TranslationValidationError("wire count mismatch")
    for source_wire, translated_wire in zip(expected_wires, raw["wires"]):
        if set(translated_wire) != {"name", "width", "expr", "cut"}:
            raise TranslationValidationError("wire schema")
        ir_node, ir_width, nodes = _parse_ir(translated_wire["expr"], widths)
        comparisons += nodes + 4
        candidate = (translated_wire["name"], translated_wire["width"], ir_node,
                     translated_wire["cut"])
        if candidate != source_wire or ir_width != source_wire[1]:
            raise TranslationValidationError("continuous equation mismatch")

    overrides = _initial_state(manifest["initial_state"])
    expected_registers = []
    for name in sorted(assigned):
        signal = module.signals[name]
        current: tuple = _variable(name)
        expression_nodes = 1
        for update in module.updates:
            if update.target != name:
                continue
            condition, cw, cn = _compile_source(update.condition, widths)
            value, vw, vn = _compile_source(update.value, widths, signal.width)
            if vw != signal.width:
                raise TranslationValidationError("source assignment width mismatch")
            current = ("mux", _as_boolean(condition, cw), value, current)
            expression_nodes += cn + vn + 1
        initial = overrides.get(name, signal.initial if signal.initial is not None else 0)
        expected_registers.append((name, signal.width, initial, current,
                                   name in manifest_cuttable))
        comparisons += expression_nodes
    if set(overrides) - assigned or manifest_cuttable - assigned:
        raise TranslationValidationError("initial/cut policy names non-register")
    if len(raw["registers"]) != len(expected_registers):
        raise TranslationValidationError("register count mismatch")
    for source_register, translated_register in zip(expected_registers, raw["registers"]):
        if set(translated_register) != {"name", "width", "init", "next", "cut"}:
            raise TranslationValidationError("register schema")
        ir_node, ir_width, nodes = _parse_ir(translated_register["next"], widths)
        comparisons += nodes + 5
        candidate = (translated_register["name"], translated_register["width"],
                     translated_register["init"], ir_node, translated_register["cut"])
        if candidate != source_register or ir_width != source_register[1]:
            raise TranslationValidationError("next-state equation mismatch")

    done_cursor = Cursor(_tokens(manifest["done_expression"]))
    source_done_expression = _expression(done_cursor)
    if done_cursor.look() is not None:
        raise TranslationValidationError("done expression trailing token")
    source_done, source_done_width, source_nodes = _compile_source(source_done_expression, widths, 1)
    translated_done, translated_done_width, translated_nodes = _parse_ir(raw["done"], widths)
    comparisons += source_nodes + translated_nodes + 2
    if source_done_width != 1 or translated_done_width != 1 or source_done != translated_done:
        raise TranslationValidationError("completion equation mismatch")

    return {
        "status": "ACCEPT",
        "case": manifest["case_id"],
        "module": manifest["module"],
        "source_blob_verified": True,
        "clock_verified": True,
        "input_domains_verified": len(source_inputs),
        "register_equations_verified": len(expected_registers),
        "continuous_equations_verified": len(expected_wires),
        "completion_equation_verified": True,
        "cut_policy_verified": True,
        "structural_comparison_units": comparisons,
        "accepted_source_subset": "restricted-single-clock-two-state",
    }
