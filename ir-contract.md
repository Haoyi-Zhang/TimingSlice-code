# Equation and certificate contract

## Source IR

The JSON top level has exactly `id`, `inputs`, `registers`, `wires`, `done`, and
`horizon`. Integers are genuine JSON integers, not Boolean values. Identifiers
are unique ASCII identifiers. No caller-supplied expression is evaluated as
Python. The checker rejects duplicate JSON keys and unsupported operators.

An input declaration is `{name, width, values}`. `values` is a nonempty strictly
increasing list within the unsigned width. Domains are independent across ports
and cycles. A register declaration is `{name, width, init, next, cut}`; a wire
is `{name, width, expr, cut}`. `cut` is Boolean. A cuttable equation is identified
by `w:<wire-name>` or `r:<register-name>`. Wires may read inputs, current registers
and earlier wires only. All next-state expressions read old register values in
the same completed combinational environment. Next states commit simultaneously.

Expression arrays:

| Form | Meaning and typing |
|---|---|
| `["const", width, value]` | Unsigned literal in its declared width. |
| `["var", name]` | Read a declared signal of its declared width. |
| `["not", a]` | Width-preserving bitwise complement. |
| `["and"/"or"/"xor"/"add"/"sub", a, b]` | Equal operand widths; result at that width. |
| `["eq"/"ult", a, b]` | Equal widths, one-bit equality or unsigned less-than. |
| `["mux", condition, yes, no]` | One-bit condition; equal-width branches. |
| `["concat", high, low]` | High operand above low operand; summed width. |
| `["slice", value, low, width]` | Contiguous slice entirely inside the operand. |

Every operation is total. Arithmetic and complement are masked to the result
width. There are no signed values, unknown/high-impedance values, memories,
multiclock behavior, asynchronous resets, nonblocking-assignment syntax, or
physical-delay semantics. The prototype acceptance envelope is 16 input ports,
128 registers, 512 expression nodes in total, word widths 1 through 16, expression
depth at most 64, and horizon 0 through 64. The campaign's actual models are much
smaller; see `input_dimensions.csv`. These constants are not the parameters in
the asymptotic complexity arguments.

The `done` expression has width one and is sampled at indices 0,...,H before
state updates. A result H+1 means no completion within this interval. Input at
sample zero is not implicitly a reset or transaction-start pulse. Changing the
initial state, environment, completion expression, horizon or observation policy
changes the proposition to be checked.

## Cut interpretation

A retained set K contains selected cuttable definitions. Noncuttable definitions
are always fixed. Each omitted wire gets one arbitrary legal word per cycle,
shared at every occurrence. Each omitted register equation chooses one arbitrary
next-state word per update. All initial register values are preserved. The
source side always uses the original equations without cuts.

## Positive certificate

A preservation certificate has exactly `kind`, `retained`, `horizon`,
`observation`, `frontiers`. The kind is `preservation`. The retained list is
sorted and unique. The observation is `first-hit` or `waveform`. The certificate
has H+1 frontier lists. Each row is `[source_register_vector,
abstract_register_vector]` in register declaration order. Every layer is sorted,
unique, correctly typed and within declared ranges. At most 50,000 rows per layer
are accepted by the prototype.

The checker verifies the initial pair, all input/wire-cut completion comparisons,
and all required next-cut successor memberships. In first-hit mode it stops a
branch after both completion bits are one; waveform mode continues. Extra safe
frontier states may be accepted. It is unsound to require only replay of a few
sampled behaviors or only existence of a successor.

## Negative and canonicality certificate

A counterexample has `kind`, `retained`, `horizon`, `observation`, `time`, `inputs`,
and `cuts`, plus `predecessors` when canonicality is claimed. The last sample is
the reported `time`. Every earlier sample must agree; a first-hit witness must
not continue after a common one. Input and cut lists have exactly time+1 entries.
Each earlier cut dictionary includes all omitted wires and all omitted
next-register equations; the last includes only omitted wires. No unused extra
assignments, undefined identifiers, or out-of-domain values are permitted.

The order is: last differing cycle; then the entire input-block list; then the
entire cut-block list. Within a block, use declaration order, with wire cuts
before register cuts. Values are unsigned. `predecessors.frontiers` contains
ordered rows `[source_state, abstract_state, input_sign, cut_sign]` at each
prefix length. Signs are -1, 0, or 1. Their independent transitions prove that
no shorter or lexicographically smaller witness exists. Replay alone does not
establish this claim.

## Bundle and emitter binding

The bundle keys are exactly `status`, `model_id`, `preservation`, `necessities`,
`timing_model`, `attempts`, and `work`. An accepted claimed status is
`inclusion-minimal` or `preserved`. Each necessity has an `equation` and a
`witness` whose retained set is exactly K minus that equation and whose
observation policy matches the positive certificate. A minimal bundle must cover
every member of K exactly once. Each necessity must carry canonicality evidence.
A preserved bundle may omit some necessity proofs, but any proofs it includes
are still fully checked.

The checker independently reconstructs zero filling, restricted constant
substitution, and transitive live-cone removal and compares the result to
`timing_model`. This equality is not a substitute for preservation; both checks
are necessary. `model_id` is a label, not a digest or semantic identity proof.
The source equations are re-evaluated directly. Informational `attempts` and
`work` do not establish claims, and the checker does not trust their contents.

## Resource outcomes and trust

`accepted: true` is returned only after all relevant obligations pass.
Insufficient work/representation budget returns UNKNOWN, not a negative or
positive mathematical verdict. Malformed supplied evidence is rejected. Source
parsing and host-language execution are not mechanized proofs. JSON file-size
checks are not a general sandbox against adversarial resource use. Use the
bounded reproduction runner or an enclosing OS policy for nontrivial workloads.

The independent acceptance path is `checker.py` plus the supplied equation
source and bundle. It imports no producer or reference-oracle module. Its trusted
computing base includes its own IR parser, stack evaluator, closure logic,
emitter reconstruction, the standard library and interpreter. The artifact also
delivers a restricted frontend for ten pinned modules and a separately written
instance validator. The validator strictly decodes the unique pinned source
bytes, requires any separately supplied text to match those bytes exactly,
parses the manifest `cuttable` field itself, and binds that candidate universe
to the delivered IR. The ten translations are additionally compared with
independent step functions. These accepted-instance checks do not establish a
general or mechanically verified Verilog-to-IR preservation theorem. See
`rtl-subset.md` for the exact grammar and exclusions.
