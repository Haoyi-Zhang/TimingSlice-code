# Literature evidence and comparison status

This file separates verified bibliographic facts, substantive full-text
calibration, abstract-level screening, and unresolved comparisons. The
manuscript cites **56 scholarly or formal-standard records**, and every
bibliography entry is cited in the text. Reference count is not used as evidence
of novelty, and no source is included merely to meet a numeric threshold.

## Anchor record

Yu Zeng, Aarti Gupta, and Sharad Malik, *Automatic Generation of Cycle-Accurate
Timing Models from RTL for Hardware Accelerators*, ICCAD 2024, article 155,
pages 155:1--155:8, DOI 10.1145/3676536.3676657.

The Princeton publication record verifies the title, three-author order, DOI,
ICCAD 2024 host proceedings, dependency-analysis/constraint-solving framing,
six-design applicability statement, and a later repository publication date.
DBLP supplies the proceedings page range and event-year record. The bibliography
uses the proceedings year 2024. No correspondence, collaboration, or approval is
inferred from author position.

Publisher, DOI, institutional, author-page, and general scholarly-search routes
did not yield the complete eight-page text in this environment. Consequently,
the paper does **not** claim to have verified that the anchor lacks internal
certificates, minimality checks, translation validation, or diagnostic
machinery. Its supported comparison is constructive and object-level: this
project defines and checks a universal-havoc, final-context-minimality,
canonical-diagnostic certificate for a supplied bounded equation model and
separately binds ten accepted source/harness instances to that model.

## Completed 12+5+5 calibration

`literature-calibration.csv` contains **22 substantive full-text calibration
rows**:

| Class | Count | Purpose |
|---|---:|---|
| Closest design automation and formal hardware | 12 | Calibrate problem framing, system/formal mechanism, evidence breadth, and closest object-level deltas |
| Influential formal methods | 5 | Calibrate checker architecture, soundness arguments, abstraction/search separation, and trust boundaries |
| Adjacent slicing, minimality, and diagnosis | 5 | Calibrate relevance criteria, inclusion minimality, irreducible explanations, and diagnostic ordering |

Each row identifies the primary paper/report URL, access date, sections
calibrated, problem, principle, correctness or performance argument, practical
connection, evaluation breadth, artifact strength, narrative sequence, and the
specific delta for this work. Accessible full text or an author manuscript was
inspected across the introduction, method/formalism, evidence, limitations, and
conclusion where available; metadata-only records were not counted. The
unavailable ICCAD 2024 anchor is excluded from the 22 rather than falsely labeled
as read.

The closest set includes ILA and application-level validation; LightningSim,
OmniSim, FireSim, and the 2026 latency-sensitive many-core model; Yosys, FIRRTL,
Kami, Sail, Rtl2lean, and Granite. The 2026 Rtl2lean and Granite papers are
particularly important adversarial comparators because they provide stronger
mechanized source/proof chains. They narrow the positioning of this project to a
different object: producer-independent evidence for a bounded dependency cut,
final-context inclusion minimality, canonical first-completion diagnostics, and
output reconstruction.

The influential set covers bounded model checking, IC3, CEGAR, translation
validation, and proof-carrying code. The adjacent set covers Weiser slicing, the
program dependence graph, inductive validity cores, minimal unsatisfiable
subsets, and QuickXplain. The IVC paper's author is correctly recorded as
**Elaheh Ghassabani**; the earlier misspelling in the bibliography was repaired.

## Bibliography organization

The 56 cited records cover five non-interchangeable roles:

| Role | Representative records | Use in this paper |
|---|---|---|
| RTL/architecture/timing extraction | Zeng et al. 2021/2022/2024; ILA/ILAng; application-level validation | closest source-to-model context and boundary |
| Timing and system simulation | LightningSim; OmniSim; FireSim; 2026 many-core model | speed/accuracy alternatives not benchmarked here |
| Hardware IR and mechanized infrastructure | Yosys; FIRRTL; MLIR; Rosette; Kami; Sail; Rtl2lean; Granite; Pono; Z3; Boolector; ABC | source/checking context and stronger trust-chain comparators |
| Verification certificates and abstraction | BDD/model checking; BMC/induction/IC3/interpolation; CEGAR/proof abstraction; PCC; translation validation; DRAT/LRAT | checker architecture and proof representation |
| Slicing, cores, diagnosis, complexity | dependence slicing; IVC; MUS/diagnosis/QuickXplain; complexity foundations | minimality, diagnostics, and hardness boundaries |

Ordinary websites, blogs, and venue pages are used only for workflow or
bibliographic verification, not as substitutes for research literature.
LightningSim, OmniSim, FireSim, and the many-core model are not executed or
presented as equal-budget baselines.

## Remaining literature boundary

The prescribed accessible-source **12+5+5 calibration is complete**. The
remaining literature hold is narrower but still material: the exact closest
ICCAD 2024 article was not read in full, so the paper cannot establish that its
certificate, minimality, source-binding, or diagnostic objects are absent from
that system. This limits external novelty positioning but does not invalidate
the bounded definitions, proofs, retained finite evidence, or accepted-instance
source claims.

## Venue record

The current first-party TCAD instructions were rechecked on 2026-09-16 for the
regular-paper length and formatting rules and the disclosure route. The project
uses the supplied unmodified IEEE journal class/style and a stricter internal
12-page target. Live selector identity and every external-use policy must be
rechecked immediately before submission. Nothing was submitted or uploaded.

## Citation-closure audit

`bibliography-audit.csv` contains one row for each of the 56 cited entries. It
distinguishes 21 cited entries with full-text calibration records, authoritative
metadata checks for recent or critical records, and canonical scholarly metadata
review. The 22-row calibration also includes QuickXplain, which is not cited in
the manuscript; the calibration-row count is therefore not the count of
full-text-calibrated bibliography entries. No citation is added just to make
those counts equal.
`results/bibliography-audit.json` confirms 56/56 cited entries, no missing keys,
and no uncited padding.
