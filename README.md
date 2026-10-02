# Proof-carrying dependency slices

This standalone repository implements and checks bounded first-completion
certificates for a typed unsigned equation IR. It contains hand-written proof
arguments, an untrusted certificate producer, a separately implemented
certificate checker, finite direct oracles, exact generated fixtures, and a
restricted public-RTL translation experiment with an independent
source-to-equation validator.

**Boundary.** The general mathematical claims concern `ir-contract.md`. The
public source experiment accepts only the syntax in `rtl-subset.md`; it is not a
general Verilog/SystemVerilog frontend, synthesis flow, simulator, or accelerator
evaluation. The Python implementation and runtime remain trusted and the proofs
are not proof-assistant mechanized.

## Reproduce from this repository root

No package installation, solver, simulator, GPU, network access, API, or file
outside this repository is required. Use Python 3 on a Unix-like system with
`resource` and `SIGALRM`; do not use Python `-O` because the assertions are
intentional. Output directories must be absent or empty.

```sh
# Static closure audit of retained core and public generation evidence
python3 verify-retained.py --out results/local-retained-audit.json

# Clean replay of all ten restricted RTL translations and retained bundles
python3 rtl-pilot.py \
  --out results/local-rtl \
  --mode replay \
  --bundle-dir results/rtl-pilot/bundles

# Direct independent replay of one retained core bundle
python3 -m src.checker \
  cases/post-completion.json results/clean-reproduction/example.json --limit 100000
```

Expected outcomes are exit 0 for all three commands, `status: PASS` for the
static closure audit, `status: PASS` and `mode: replay` for the public-RTL run,
and `accepted: true` for the direct checker replay. Checker exit codes are 0
accepted, 1 rejected, and 2 unknown. Too little work returns UNKNOWN rather than
a convenient verdict.

The standard-library software regression suite and release audits are:

```sh
python3 run-tests.py --out results/local-software-regression.json
python3 audit-bibliography.py \
  --tex ../paper/main.tex --bib ../paper/references.bib \
  --calibration literature-calibration.csv \
  --out results/local-bibliography-audit.csv \
  --summary results/local-bibliography-audit.json
python3 verify-paper-data.py --project-root .. \
  --out results/local-paper-data-audit.json
python3 verify-release.py --project-root .. \
  --out results/local-release-audit.json
```

The retained full equation campaign and public generation are also reproducible,
but repeating either would exceed the frozen cumulative campaign budget. Their
prior clean outputs and command receipts are retained in
`results/clean-reproduction/` and `results/rtl-pilot/`:

```sh
python3 reproduce.py --out results/local-core
python3 rtl-pilot.py --out results/local-rtl-generation --mode generate
```

The runners use one process, a 1 GiB address-space limit, bounded CPU time, and a
118-second wall alarm. The direct CLI invocations have semantic-work limits but
should still be placed under an OS policy for hostile large inputs. The checker
also limits JSON size and frontier layers as described in `ir-contract.md`.

## Evidence map

- `proofs/theory.md`: stop-frontier soundness and bounded completeness,
  deterministic output binding, final-context inclusion minimality, canonical
  witness exclusion, and three complexity reductions. These are hand proofs.
- `src/producer.py`: untrusted search, minimization, certificate generation, and
  restricted timing-model emission.
- `src/checker.py`: independent equation parser/evaluator, positive frontier
  checking, negative/canonical witness checking, and output reconstruction.
- `src/rtl_frontend.py`: restricted untrusted RTL-to-equation translator.
- `src/rtl_translation_checker.py`: separately implemented source parser,
  compiler, blob/harness binder, and exact translation validator. It strictly
  decodes the pinned source bytes, requires redundant caller text to match,
  parses the manifest candidate set internally, and imports neither the
  translator nor either bundle component.
- `tests/oracles.py`: direct transition formulas for 13 semantic controls and
  truth-table oracles for 96 reduction instances.
- `rtl-pilot.py`, `public_rtl/yosys/`: ten pinned public modules, exhaustive
  bounded reference functions, translation validations, mutations, and bundles.
- `results/clean-reproduction/`: current core results and clean direct-CLI runs.
- `results/rtl-pilot/`: retained expanded public-RTL generation evidence.
- `results/clean-rtl-replay/`: clean replay of the ten translations and four
  retained bundles.
- `verify-paper-data.py` and `results/paper-data-audit.json`: static
  reconciliation of every plotted frontier series, all 13 control-table rows,
  all ten public-RTL table rows and totals, certificate-control counts,
  bibliography closure, and manuscript campaign accounting.
- `claim_evidence_ledger.csv`, `external_resources.csv`,
  `input_dimensions.csv`, `literature-status.md`, and
  `literature-calibration.csv`: claim-to-evidence, acquisition/license,
  dimension, literature-boundary, and completed 12+5+5 calibration records.

## Retained results

The core campaign contains 109 generated models, 928 retained-subset queries,
96 checked reduction conditions, 26 accepted control bundles, 35 canonical
necessity witnesses, 5,401 mixed retained/cut transition comparisons, and 2,410
operator checks. Sixteen invalid certificate mutations are rejected, one sound
superset is accepted, and two zero-budget controls return UNKNOWN.

The public-RTL generation consumes ten exact target modules from one pinned Yosys
commit. A separate translation validator accepts all ten blob/harness/IR
bindings and performs 601 internal structural comparisons. Exhaustive reference
replay covers 1,377 traces and 4,965 complete-state/completion samples. Four
one-candidate inclusion-minimal bundles are accepted by the independent checker.
Three dynamic mistranslations are detected after 2, 2, and 51 paired samples,
and eight retained source/harness/equation binding mutations are rejected. The
review repair additionally rejects an independent source-byte substitution and
two joint substitutions that previously escaped the validator: detached altered
text plus matching altered IR with the real bytes unchanged, and an external
empty candidate set plus matching `cut=false` IR while the manifest still names
the candidate. The repair does not imply that the retained ten translations or
trace data were wrong. These are finite results for the documented fragment,
not a general source-language theorem.

The post-completion control remains an adverse result: one retained equation
creates 33 frontier pairs and 338 positive obligations, while retaining all three
under first-hit observation creates 5 pairs and 16 obligations; waveform
preservation with all three creates 9 pairs and 32 obligations. Fewer equations
do not imply a smaller proof or less checking work.

## Interpretation, accounting, and licenses

A cut assigns one shared arbitrary value to an omitted definition for a cycle;
it is not per-use nondeterminism, fixed zero, deletion of initialization, or a
change in the input environment. Inclusion minimality is relative to the final
retained set, declared candidates, havoc abstraction, horizon, and observation;
it is not minimum cardinality or program optimality.

The corrected retained accounting reaches 149,999 semantic units before this
review repair. The historical 19-test regression is 102 rather than 83 units:
the old subtotal omitted ten accepted translation validations, eight recorded
binding mutations, and one independent source-byte substitution check. Two
actual pre-fix risk probes and the 21-unit post-fix targeted translation
regression bring the executed total to 150,022, exceeding the 150,000 planning
ceiling by 22. No historical minimization or large search was rerun. Internal
translation-AST comparisons, parsing-only tests, compilation, documentation,
rendering, and packaging are reported separately and not double-counted. See
`pilot-protocol.md`, `results/campaign-accounting.json`, and
`results/translation-static-risk-repair-summary.json`.

Original code, generated fixtures, proofs, and documentation use the included
MIT license. Unmodified Yosys sources are redistributed with
`public_rtl/yosys/LICENSE-ISC.txt` and exact provenance in the manifest. No
scholarly article, solver, interpreter binary, or font is redistributed.

ChatGPT was used substantively for formulations, proofs, code, experiments,
literature synthesis, and writing. Human approval and external-use policy
compliance remain unresolved. Nothing was contacted, uploaded, published, or
submitted by this project.
