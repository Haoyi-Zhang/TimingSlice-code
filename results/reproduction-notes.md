# Reproduction and campaign accounting

## Clean extraction

The scientific source and stored inputs were archived and extracted into a fresh
standalone repository root before the following commands were executed. No file
outside that root was read by the scientific programs. The command output path
was `results/local`; its resulting contents were copied, without scientific
re-execution, to the retained `results/clean-reproduction` directory. The
scientific source, tests, runner, and fixtures in the delivered repository are
byte-for-byte the same as the clean execution inputs; later edits were to
explanations, proof presentation, and packaging only.

```sh
python3 reproduce.py --out results/local
python3 -m src.producer cases/post-completion.json results/local/example.json --limit 100000
python3 -m src.checker cases/post-completion.json results/local/example.json --limit 100000
```

All three exits were 0. The pilot reported PASS with research gate HOLD. The
producer emitted an inclusion-minimal bundle and the separate checker accepted
it. The exact commands, stdout, stderr, limits, and per-child process measurements
are retained in `clean-reproduction/cli-runs.json`. The pilot's own interval,
measured after its imports and setup, is in `clean-reproduction/run.json`.
Do not conflate these two measurement scopes.

| Command | Exit | Whole-child wall seconds | Whole-child CPU seconds | Peak RSS (KiB) |
|---|---:|---:|---:|---:|
| Fixed pilot | 0 | 1.040472418 | 1.434798000 | 98344 |
| Producer example | 0 | 0.653016247 | 1.113341000 | 92972 |
| Checker example | 0 | 0.659645543 | 1.029769000 | 92716 |

The internal pilot interval was 0.371379720 wall seconds and
0.371680981 CPU seconds. These are one-run resource observations, not
repeated performance estimates, simulator throughput, or confidence intervals.
The outer runner collected each child with `wait4`, rather than assigning
cumulative child RSS to each run. Whole-child CPU includes interpreter startup
and can exceed the instrumented scientific interval. The scientific algorithms
use one worker. Every clean command had a 1 GiB address-space cap, 90-second soft
CPU limit, 95-second hard CPU limit, and 118-second wall limit; none timed out.

## Recorded semantic work

The counter below adds observations and successors from the producer/checker,
and paired direct-oracle comparisons. It deliberately counts more than the
number of top-level model queries. A paired oracle comparison exercises both
implementations but is one recorded semantic unit; it is not an instruction
count. Operator and regression checks are included in the oracle category.

| Stage | Recorded units |
|---|---:|
| Initial fixed pilot | 52313 |
| Focused mixed-context coverage repair | 5402 |
| Repaired clean pilot | 55379 |
| Separate producer CLI | 6416 |
| Separate checker CLI | 535 |
| Cumulative | 120045 |
| Campaign cap | 150000 |

The clean pilot's 55379 units comprise
26575 producer, 14624
checker, and 14180 direct-oracle units.
The initial pilot left over one quarter of the 150000-unit envelope for repair
and clean reproduction; the reservation was actually used, not just proposed.
No scientific command was rerun to obtain a favorable observation. All 109 base
models were generated, and no public RTL module was evaluated.

Available per-stage recorded CPU totals sum to 3.957145545 seconds. The initial
pilot and focused-repair records measure their instrumented intervals, while the
clean commands additionally have whole-child measurements. Thus this sum is a
mixed-scope recorded total, **not** a falsely precise whole-campaign CPU audit.
Small uninstrumented intake/packaging work is not included. Every recorded run
was far inside the per-run limits and the 6 CPU-hour project ceiling. The maximum
recorded scientific peak RSS was 98344 KiB.

## Repairs and evidence freshness

The original semantic test enumerated all-cut contexts only (2368 paired
transitions). That could conceal a faulty retained equation. The repaired test
includes retained, cut, and mixed contexts (5401 paired transitions), and an
additional known old-state wiring mutant must disagree with the direct oracle.
The focused repair and current full run both detected that mutant. This is a
finite falsifier, not a proof of every accepted equation model.

A new fixed-retained-set post-completion diagnostic separates stopping from
nondeterministic state growth. Its independently checked baseline has five
frontier entries and 16 preservation obligations. The smaller first-hit slice
has 33 entries and 338 obligations; the waveform slice has nine entries and 32
obligations. These are exact fixture costs, not a claim of faster checking.

After all three successful scientific commands, an accounting-only packaging
assertion initially failed because it assumed work objects had no `limit`
metadata field. The repair summed the named `observations` and `successors`
fields from the existing outputs. No scientific result changed, no command was
repeated, and the event is recorded in `clean-reproduction/accounting-repair.json`.

## Reproducibility scope

Logical counts, fixtures, decisions, certificates, and emitted models are
expected to reproduce exactly from the delivered standard-library source.
Wall time, CPU time, peak RSS, whitespace in interpreter errors, and externally
hosted literature availability are not expected to be byte-identical. Exact
consumed generated inputs are retained; no checksum, commit, toolchain fingerprint,
private environment cache, or interpreter binary is required. The mathematical
proof notes are hand arguments. Reproduction does not establish frontend
correctness, scholarly novelty, external human review, or TCAD readiness.

## Restricted public-RTL extension

After the core source and results were frozen, the project added a separate
restricted source-to-equation campaign. The first development and clean runs each
covered five Yosys sources and consumed 4,538 semantic units. They are retained
in the campaign account as historical development evidence but are superseded by
the expanded ten-target results for manuscript claims.

The final expanded campaign retains ten unmodified Yosys target modules at
commit `d0e71cfb7bcafe2b437f3edc1789b69e99ecd55a` and the exact ISC notice under
`public_rtl/yosys/`. The restricted frontend and transaction harnesses are
separate from the unchanged core producer/checker. A second parser/compiler in
`src/rtl_translation_checker.py` imports neither the frontend nor the
producer/checker; it independently verifies exact Git blob identity, source
bytes, clock, input domains, initial state, horizon, completion expression, cut
policy, and canonical equation IR.

The expanded generation run exits zero and reports:

- 10 accepted source/harness/IR validations and 601 internal structural
  comparisons;
- 1,377 traces and 4,965 complete-state/completion sample checks;
- four accepted one-candidate inclusion-minimal bundles;
- three detected dynamic translation faults after 2, 2, and 51 samples;
- eight rejected source/harness/equation binding mutations;
- 8,556 producer and 828 checker obligations;
- 14,422 non-overlapping semantic units.

A clean standalone replay, without repeated minimization or mutation generation,
also exits zero. Its retained command is:

```sh
python3 rtl-pilot.py \
  --mode replay \
  --retained results/rtl-pilot \
  --out results/clean-rtl-replay
```

The replay verifies all ten exact blobs/translations, all 4,965 samples, and all
four retained bundles in 5,803 semantic units. `clean-rtl-replay/run.json` records
one worker, the bounded child process, wall/CPU measurements, and peak RSS. A
separate static closure audit reports `PASS` without repeating scientific search.
Finally, one retained core bundle is directly checked once more; the checker
accepts it with 198 observations and 337 successors (535 semantic units). A
three-bundle pre-release probe consumes 16 additional units. The retained
19-test standard-library regression is retrospectively corrected from 83 to 102
semantic units: ten accepted translation validations, eight recorded binding
mutations, and one independent source-byte substitution check had been omitted
from the subtotal. The historical full suite was not rerun for this correction.
Two actual pre-fix risk probes and a five-method, 21-unit post-fix translation
regression are recorded separately.

Final campaign accounting is:

| Stage | Semantic units |
|---|---:|
| Core campaign | 120045 |
| Earlier five-source development run | 4538 |
| Earlier five-source clean run | 4538 |
| Expanded ten-target generation | 14422 |
| Expanded clean replay | 5803 |
| Final retained core checker replay | 535 |
| Pre-release three-bundle probe | 16 |
| Retained 19-test software regression, corrected | 102 |
| Pre-fix static-risk probes | 2 |
| Post-fix targeted translation regression | 21 |
| **Cumulative executed** | **150022** |
| Original planning cap | 150000 |
| **Overrun from required repair validation** | **22** |

Internal translation-AST node comparisons, compilation, documentation,
rendering, and packaging are reported separately and are not double-counted as
scientific semantic work. No historical minimization or large-search command was
rerun for the repair.

The accepted source instances do not establish unrestricted parsing,
proof-assistant correctness of either parser, equivalence to a third-party
Verilog simulator, accelerator workload coverage, physical timing, or speedup.
Their purpose is to provide a precise, licensed, independently bound and
falsifiable source-to-certificate pilot without broadening the theorem beyond the
documented fragment.
