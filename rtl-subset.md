# Restricted public-RTL translation contract

The public-RTL experiment exercises an actual source boundary without claiming a
production Verilog/SystemVerilog frontend. `src/rtl_frontend.py` accepts only the
syntax needed by the ten exact target modules in
`public_rtl/yosys/manifest.csv`. Unsupported constructs are rejected rather than
approximated. Each manifest row binds the repository commit, exact Git blob,
target module, clock, finite input domains, initial state, transaction-completion
expression, horizon, and candidate cut policy.

## Accepted source fragment

- One selected module and one positive-edge clock. Other modules in the same
  source file are ignored only after exact target-module token extraction.
- ANSI or old-style scalar/vector `input`, `output`, `wire`, and `reg`
  declarations with literal `[msb:0]` ranges.
- Nonnegative sized binary/octal/decimal/hex literals and nonnegative unsized
  decimal literals that fit the inferred or declared unsigned context width.
  An unsized decimal that would require truncation is rejected, including in
  comparisons; the frontend does not implement general Verilog operand
  extension. Logical operators evaluate each operand's nonzero value before
  combining them, without narrowing one operand to the other's width.
- Identifiers, parentheses, unary `-`, `!`, and `~`; selected Boolean,
  comparison, addition, and subtraction operators; and ternary expressions.
- `always @(posedge clock)` with nested or named `begin/end`, `if/else`, simple
  priority `case`, and nonblocking assignments. A default item is active only
  when no explicit item matches, regardless of its textual position. Each
  register has exactly one procedural driver; separate blocks may drive
  disjoint registers. Repeated assignments within one block preserve the last
  executed nonblocking assignment.
- Constant declaration/`initial` assignments used by the fixed examples.
- Direct continuous assignments to declared wires for the exercised case.
- `assert`, `assume`, and `cover` statements are skipped because the translated
  object is the transition relation, not the source property language.

The lowering preserves old-state reads and simultaneous nonblocking updates,
coerces arithmetic to declared unsigned widths, and emits the typed equation IR
specified in `ir-contract.md`. Completion, horizon, domains, initialization
overrides, and cut candidates are explicit harness data; they are not inferred
from arbitrary RTL intent.

## Independent translation validation

`src/rtl_translation_checker.py` is a second implementation of the accepted
source semantics. It imports neither `rtl_frontend`, the bundle producer, nor the
bundle checker. For every manifest row it:

1. strictly decodes the consumed source bytes as UTF-8, requires any separately
   supplied source text to be byte-identical after decoding, and recomputes the
   exact Git blob identifier;
2. independently lexes and parses the selected source module;
3. checks clock, finite input-domain, initial-state, horizon, completion, and cut
   bindings against the manifest; in particular, it parses the manifest
   `cuttable` field internally and uses that set as the candidate universe;
4. compiles source expressions through a separately written canonical compiler;
5. independently parses the delivered equation IR; and
6. requires exact canonical equality for every register next-state equation,
   continuous equation, declaration, and completion equation.

The reported 601 internal node comparisons are a diagnostic, while campaign
accounting counts one accepted translation-validation obligation per pinned
module. Eight retained fixed mutations cover source identity, source bytes,
horizon, input domains, initialization, cut policy, completion, and
case-priority lowering; all are rejected. A separate source-byte substitution
test and two post-review joint substitutions are also rejected: detached source
text plus matching altered IR cannot inherit the real source-byte hash, and an
external empty candidate set plus matching `cut=false` IR cannot replace a
manifest that still declares the register cuttable. These controls harden the
validator; they do not show that the retained ten translations were erroneous.

Six owned source-semantics regressions in `tests/test_source_semantics.py`
cover default-first/middle/last selection, a nested conditional under an early
default, explicit-label priority, same-block assignment order, and disjoint or
conflicting procedural drivers. They check 78 state/input contexts through both
IR interpreters, seven source/IR bindings, and two multiple-driver rejections.
These checks repair a shared case-default mistake and exclude cross-block
assignment races; they neither change the pinned translations nor establish
general frontend correctness.

A second path exhaustively enumerates every manifest trace through the horizon
and compares the complete translated register vector and completion bit with
separately written transition functions. This path detects three fixed dynamic
mistranslations. The two paths are complementary: structural validation checks
exact source/IR binding, while bounded replay provides an independently written
semantic oracle for the exercised harnesses.

## Explicit exclusions and trust boundary

No memories or arrays, signed or four-state semantics, asynchronous or multiple
clocks, delays, blocking sequential updates, loops, tasks, functions, general
module hierarchy, parameter elaboration, generate constructs, latches, or
unrestricted SystemVerilog are supported. There is no synthesis tool or
third-party simulator in the acceptance path.

Acceptance is therefore a translation-validation result for ten pinned modules
inside this documented fragment, not a theorem about all Verilog. The two source
parsers, their canonical compilers, the equation checker, Python runtime, and
host remain trusted code; none is proof-assistant mechanized. A shared mistake in
the published fragment could affect both implementations. Those boundaries are
reported rather than hidden behind the word “verified.”
