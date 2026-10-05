# Fixed protocols and accounting boundaries

Two bounded protocols are retained: the original equation-IR campaign and an
expanded restricted public-RTL experiment. Both are deterministic,
single-worker, standard-library experiments. Neither is an industrial
performance benchmark.

## Equation-IR campaign

The source language is the typed unsigned transition contract in
`ir-contract.md`: fixed initialization, acyclic combinational equations,
simultaneous updates, independent finite input domains, and a unary horizon.
The fixed falsifiers are:

1. Havoc cuts must be monotone and a purported positive certificate may not miss
   an exhaustively differentiating trace.
2. First completion may omit state needed by the complete completion waveform.
3. Individually safe omissions need not compose.
4. Fixed-zero replacement is nonmonotone on the XOR control.
5. Replay alone must not establish canonicality; a nonleast prefix must fail.
6. The validity, inclusion-minimality, and size-bounded-existence reductions must
   match direct Boolean truth-table oracles.
7. A retained old-state wiring mutant must be detected in mixed retained/cut
   contexts.

The 13 named controls are fixed in `src/cases.py`. Reduction coverage comprises
all 16 two-input truth tables for validity, all 4 x 4 one-input table pairs for
minimality, all 16 one-existential/one-universal tables, all 16
two-existential/no-universal tables, and the fixed arithmetic subset
`sorted({0,255} | {(73*i+19) % 256 for i in range(30)})` for the remaining
existential-universal family. Every retained subset is checked. Finite checks
validate constructions; they do not establish the asymptotic theorems.

The initial run covered all-cut contexts only. The repaired and clean runs cover
retained, cut, and mixed contexts and add the old-state mutant. The initial
`results/observed` directory is historical evidence and is not cited as current
coverage. A post-completion diagnostic adds a fixed-retained-set baseline to
separate the first-hit stopping rule from extra abstract-state freedom.

## Restricted public-RTL protocol

The expanded source set contains ten unmodified target modules from Yosys commit
`d0e71cfb7bcafe2b437f3edc1789b69e99ecd55a`. Exact paths, Git blob identifiers,
transaction harnesses, and candidate policies are frozen in
`public_rtl/yosys/manifest.csv`; the accepted grammar and exclusions are in
`rtl-subset.md`.

Every source passes two acceptance paths. First, a separately implemented
translation validator binds the exact source blob and manifest to every equation
of the produced IR. Second, all finite input traces through the declared horizon
are enumerated and the translated IR's complete register state and completion
bit are compared with a separate hand-written step function. The reported run
contains 1,377 traces and 4,965 state/completion samples across all ten modules.

Four counter models also require an inclusion-minimal first-completion bundle
for their sole candidate register equation. The retained generation run executes
the producer and independent checker; clean reproduction replays those exact
bundles with the checker without repeating minimization. This separates
reproduction from a second scientific search and avoids double-counting producer
obligations.

Three dynamic negative controls remove an enable hold, invert reset priority,
and replace an old-register dependency; each must produce a mismatch. Eight
translation-binding mutations change source identity/bytes, horizon, input
domains, initialization, cut policy, completion, or case priority; each must be
rejected by the independent validator. No favorable compression, speedup, or
certificate-size threshold is required.

The retained generation reports 10 accepted source validations, 601 internal
structural comparisons, 4,965 full-state/done samples, 55 paired dynamic-fault
samples, 8 binding-mutation checks, 8,556 producer obligations, and 828 checker
obligations. Under the campaign rule, the generation therefore contributes
14,422 semantic units; the 601 internal AST comparisons remain a diagnostic and
are not counted again as 601 separate source-level obligations.

## Resource and outcome rules

Each runner uses one worker, a 1 GiB address-space limit, bounded CPU time, and a
118-second wall alarm. No swap, GPU, external compute, model API, paid tool,
private data, device, or new human evidence is used. Implementation caps are at
most 128 registers, 512 expression nodes, 16 input ports, 16-bit words, and
horizon 64; they are safeguards, not theorem parameters. Insufficient semantic
work returns UNKNOWN.

The completed core campaign accounts for 120,045 units. The earlier five-module
development and clean runs account for 4,538 each. The expanded generation adds
14,422; the final clean replay adds 5,803; the retained direct checker replay
adds 535; and the three-bundle pre-release probe adds 16. A retrospective audit
corrects the retained 19-test regression from 83 to 102 units by including ten
accepted translations, eight binding mutations, and one independent source-byte
substitution check. The corrected historical freeze is therefore 149,999. The
review then executed two pre-fix risk probes and a 21-unit post-fix targeted
translation regression, producing **150,022 semantic units in total**, or 22
above the original 150,000 planning ceiling. No historical minimization or large
search was repeated. Compilation, documentation, rendering, static audits, and
packaging are excluded. `results/campaign-accounting.json` records every
component and the overrun explicitly.

A PASS means only that the fixed finite protocol succeeded. It does not establish
unrestricted RTL translation, third-party simulator equivalence, accelerator
workload relevance, proof compactness, novelty over inaccessible full text,
or external replication.
