# First-completion equation cuts: definitions, proofs, and counterexamples

These are mathematical arguments for a finite equation semantics. They are not
proof-assistant-checked theorems about the Python implementation, and they do not
establish a general Verilog frontend theorem. The artifact does deliver a
restricted frontend plus a separate accepted-instance validator for ten pinned
modules; that finite evidence binds only those source/harness/IR instances.
Finite experiments exercise the constructions; they are not the proofs. The monotone core argument
is an adaptation of the established inductive-validity-core principle, not a
novelty claim: Ghassabani, Gacek, and Whalen, FSE 2016,
DOI 10.1145/2950290.2950346, Section 4.

## 1. Model and observation contract

A source consists of a fixed initial register vector q0, an ordered list of
combinational equations, simultaneous next-register equations, a one-bit
completion expression D, and a horizon H. All values are finite unsigned bit
vectors. Combinational expressions may refer to inputs, current registers, and
previously declared wires; next-state expressions use that same current-cycle
environment, never partially updated registers. Arithmetic is modulo the result
width. Comparisons are unsigned. All operators are total. Input port j has a
nonempty, explicitly declared finite domain Uj. At each cycle the legal input
set is their Cartesian product U, independent of earlier inputs or states.

A sample at time t is taken after evaluating the current combinational equations
and before committing the next state. The first sample has index zero. A trace
has samples 0 through H, hence H+1 samples and at most H state updates. Its
capped first-completion time is

    tau_H = min({t in {0,...,H}: D_t = 1} union {H+1}).

The H+1 value means no completion within the horizon; it is not a claim about
completion afterward. A transaction is the fixed initial state, input contract,
observation expression, and horizon together. There is no implicit launch,
handshake, reset pulse, liveness assumption, or observation after the horizon.
A synchronous reset can be represented explicitly in a next-state expression.
An asynchronous reset is outside the semantics.

Let E be the declared set of cuttable equations, with all other equations fixed.
A retained set K is a subset of E. In A_K, each omitted wire equation supplies a
fresh arbitrary word at each sample. A wire's value is shared by every use of
that wire in that sample. Each omitted register equation supplies an arbitrary
next-state word at each update. Initial register values remain q0 even if their
next-state equations are omitted. A cut register's value is stored and shared
throughout the next sample, not re-havoced at each expression occurrence.

Let B_K(u) be the finite abstract behaviors for an input trace u. The full source
has one behavior S(u). Define

    Valid_H(K) iff for every u and every a in B_K(u),
                         tau_H(a) = tau_H(S(u)).

The waveform variant instead requires equality of D at every sample 0,...,H.
Both relations use the same source and the same declared inputs. Neither permits
replacing the source with the proposed timing model during checking.

## 2. Lemma 1: weakening equations is monotone

For K1 subset K2, B_K2(u) is a subset of B_K1(u), for every legal u. Moreover,
S(u) belongs to B_K(u) for every K.

Proof. Take any behavior of A_K2. For every equation that is fixed in A_K2 but
omitted in A_K1, choose its original value along this behavior as its havoc
value. Induct through the topologically ordered wires in each cycle. Every
previous wire, input and current register then agrees, so every retained wire
also agrees. The newly omitted wires agree by the chosen havoc values. The same
argument for all next-state equations simultaneously preserves the next register
vector. Start from the identical fixed initial state and induct on cycles.
Choosing source values for every omitted equation gives the second assertion.
No choice changes a legal-input predicate, because that predicate is fixed and
independent of K. QED.

Corollary. If Valid_H(K1), then Valid_H(K2) whenever K1 subset K2. Equivalently,
invalidity is downward closed. The same statements hold for the waveform
variant. This is monotonicity in retained equations, not in arbitrary program
rewrites or constant replacements.

## 3. Theorem 1: stop-frontier certificates

Write Q for the finite source register space, also used by the abstract system.
A certificate contains F_0,...,F_H, with F_t a set of pairs in Q x Q. A pair
(s,a) represents source and abstract states before sample t, along a history
that has not jointly completed at an earlier sample. The checker need not trust
this interpretation: it establishes the following obligations itself.

1. F_0 contains (q0,q0).
2. For every t, every (s,a) in F_t, every legal input u and every current wire-cut
   assignment v, evaluate the original source and A_K. Their completion bits
   must agree.
3. When t < H and these bits are both zero, every next-register-cut assignment
   must lead to a pair in F_(t+1).

No successor is required after simultaneous completion, or after sample H.
For waveform certificates, replace the zero-bit restriction in rule 3 with no
restriction on the common bit. Frontier supersets are permitted, provided all
three obligations hold; syntactic differences in a certificate are not by
themselves errors.

Soundness. If these obligations hold, Valid_H(K).

Proof. Fix any legal input sequence and any abstract choices. Initially the
paired states belong to F_0. Suppose no earlier sample completed either system.
By induction their current pair belongs to F_t, so rule 2 makes the current
completion bits equal. If they are one, both first-completion times are t and
later behavior cannot change either first time. If they are zero and t < H,
rule 3 covers the actual next-cut assignment and places the next pair in
F_(t+1). If both remain zero through H, both capped times are H+1. These cases
cover every behavior. The waveform proof uses rule 3 even after a common one.
QED.

Bounded completeness of the uncapped certificate relation. If Valid_H(K), there
exist finite frontiers satisfying the rules.

Proof. At each t take exactly the pairs reachable by prefixes with no previous
joint completion. They include the initial pair and are successor-closed as
specified. If an observation disagreed at any such pair, append the input and
current cut assignment producing that disagreement. Earlier completion samples
were equal and zero, so one first-completion time is t and the other is greater
than t. Every legal extension produces a differing capped time, contradicting
validity. Thus observation agreement holds. There are only finitely many
pairs and layers. QED.

This completeness statement removes implementation limits. The prototype's
50,000-row limit per layer and semantic-work budget may return UNKNOWN even
for a valid slice. The prototype is not an always-deciding scalable verifier.

Size and work. With R register bits, |Q| = 2^R and the explicit certificate needs
at most (H+1)|Q|^2 pair entries. Let W and N be the total omitted wire and
next-register widths, respectively, and M the cost of one model evaluation.
A simple upper bound on verification work is

    O(M * sum_t |F_t| * |U| * (2^W + 2^(W+N))).

Terminal samples, completed branches, and absent register cuts reduce this
bound. It is exponential in state and free-input/cut width in the worst case.
A small number of certificate rows alone is not evidence of cheap checking.

## 4. Theorem 2: binding a deterministic timing program

First replace each omitted wire and next-register equation by the literal zero
of its declared width, preserving all initial values. Call this program Z_K.
At every step choose zero for the corresponding abstract cuts. Thus each trace
of Z_K is a behavior of A_K. By Theorem 1, a valid certificate for K implies
first-completion preservation by Z_K; the analogous result holds for waveforms.

The prototype then performs only the following restricted simplifications.
A register whose rewritten next expression is already the literal equal to its
initial value is replaced by that value. Literals are propagated forward through
wire definitions and into next-state and completion expressions. An all-literal
expression is evaluated using the declared bit-vector operator; a literal mux
condition selects its branch. Finally the transitive syntactic cone of the
completion expression, including dependencies through next-state equations, is
retained. Inputs and their domains remain in the emitted model.

Proof of the simplifications. A register removed by the first rule has the same
literal at time zero and every later time, by induction. Replacing its uses is
therefore valid at every sample. Literal wire propagation is valid by induction
on wire declaration order; all operators are total and use the declared widths.
Mux branch selection does not discard an observable effect, since expressions
are pure and total. A retained variable's defining expression has no dependency
outside the final transitive live set, except an input or a substituted literal.
Induct on wire order and clock steps to show equality of every live value with
the corresponding value of the unsimplified Z_K. The completion expression is
live, so its samples agree. Composition with membership in A_K proves the
claim. QED.

The checker reconstructs this restricted transformation separately and compares
the supplied timing program with its result. A certificate for K is not silently
attached to an unrelated output program. The emitted model remains equation IR;
no claim is made about a downstream C, Verilog, or simulator backend.

A valid havoc slice is sufficient for this zero-filled program to preserve the
observation; it is not necessary. An unsafe abstract cut can still have a safe
particular zero-filled implementation. Consequently the reported inclusion
minimality is relative to havoc cuts, not to every equivalent deterministic
program, live equation set, or machine-code implementation.

## 5. Theorem 3: certifying inclusion minimality

Suppose a stop-frontier certificate establishes Valid_H(K). For every e in K,
suppose there is a legal input/cut prefix in A_(K minus {e}) that has a first
completion disagreement with the source: all preceding observations are equal
and zero, and the last observations differ. Then K is inclusion-minimal: no proper
subset of K is valid. Conversely, if K is inclusion-minimal, such a finite
witness exists for every e in K.

Proof. A prefix with earlier equal-zero observations and a differing last
observation extends to a behavior with different capped first time. Thus every
single deletion K minus {e} is invalid. If a proper subset J of K were valid,
choose e in K minus J. Because J subset K minus {e}, Lemma 1 would make that
single deletion valid, a contradiction. Conversely, minimality makes every
single deletion invalid. Finite bounded invalidity supplies a behavior with
different capped first times; its earliest differing completion sample supplies
the required prefix. The waveform proof instead selects its first differing
waveform sample. QED.

A greedy pass starts with E and retains an omission exactly when it is proved
safe. With an exact terminating validity oracle, any final kept equation failed
a deletion test in a superset of the final K. Downward closure keeps that test
invalid in the final context, so the result is inclusion-minimal. Nevertheless,
this implementation regenerates witnesses in each final context. This avoids
presenting a counterexample for a stale, larger retained set, and it permits a
canonicality statement for the actual delivered context. UNKNOWN is never used
as evidence of either validity or necessity. A fully certified preserved result
without every necessity proof is labeled `preserved`, not `inclusion-minimal`.

## 6. Theorem 4: shortest and lexicographically least witnesses

Fix the source, horizon, observation policy and retained set. A witness ending
at cycle d has input blocks u_0,...,u_d. Each earlier cut block lists current
wire cuts followed by next-register cuts, each in source declaration order.
The last cut block lists only current wire cuts, because a next-state value
after the last sample cannot affect the disagreement. Values are ordered as
unsigned integers. Compare witnesses by:

    (d, entire input-block sequence, entire cut-block sequence).

This order is input-primary across the whole prefix, not a per-cycle interleave
of input and cut priority. There are finitely many prefixes at each d and a
unique least tuple whenever a disagreement exists.

Replay proves that a supplied prefix differentiates; it does not prove that an
earlier or smaller prefix does not differentiate. The exclusion certificate
contains G_0,...,G_d. A row is (s,a,alpha,beta), where alpha and beta are -1, 0 or
+1, describing the comparison of the input and cut prefixes with the supplied
witness prefixes. Initially the states are q0 and both signs are zero. Extending
a sign with a block leaves a nonzero sign unchanged; a zero sign becomes the
comparison of the new blocks. The checker validates this update, rather than
accepting the signs as assertions from the producer.

The checker replays the candidate and checks the following closure rules.
At every t < d and every current input/wire-cut valuation from a row, differing
completion bits are forbidden, regardless of either sign. Equal-one samples
terminate that branch for the first-hit policy. All other nonfinal branches
must have a successor row for every next-register-cut valuation, with both
signs updated against the complete block at t. At t=d there is no successor
obligation. A disagreement is forbidden whenever alpha is negative, or alpha
is zero and beta is negative, after updating the final input and wire-cut
blocks.

Soundness. If replay and these exclusion rules pass, the supplied prefix is the
least witness under the stated order.

Proof. Induction from the initial row proves coverage of all legal pending
prefixes of each length, together with their correct signs. A shorter witness
would disagree at t<d from a covered row and violate the first rule. A witness
of length d+1 with a smaller whole input prefix has a negative final alpha.
When the whole input prefixes agree, a smaller whole cut prefix has alpha zero
and negative beta. Either case violates the final rule. Replay supplies the
claimed actual disagreement, so it is the least. QED.

Completeness of the uncapped relation. For a least witness, take exactly all
reachable ordered rows before the final sample. No shorter disagreement exists,
and no smaller final tuple disagrees, so the rules hold. At most
9(d+1)|Q|^2 rows are needed; the nine-factor counts the two independent signs.
Transition enumeration can still be exponential. A capped checker may return
UNKNOWN. The exclusion certificate is not a purported polynomial UNSAT proof.

Producer history merging. For a fixed paired state and layer, the search keeps
the least pair (input prefix, cut prefix). Any common future input/cut suffix
can be appended to every history at that pair because future equations depend
only on the paired states and current input/cuts, and the environment has no
hidden history. If input prefixes differ, their earlier comparison dominates
every suffix. If they agree, compare the full future input sequences first;
with a common suffix those also agree, leaving the cut-prefix comparison to
dominate a common cut suffix. Thus a discarded larger history cannot lead to a
smaller witness than the retained history with the same suffix. Stopping at the
first layer with a disagreement establishes shortest length. The independent
checker does not rely on this merging argument to accept canonicality.

These witnesses localize the earliest timing disagreement for a stated deletion
context. They do not rank equations by causal responsibility, prove a unique
root cause, or show that the original hardware has a defect.

## 7. Theorem 5: complexity already at an acyclic sample

This section concerns a parameterized family with circuit descriptions and
unary horizons, not the prototype's fixed model-size caps. The representation
size counts individual state and signal bits and Boolean-circuit gates; a huge
word width is not treated as a constant-size binary numeral. All hardness
constructions below already use one-bit values, H=0, no registers, and acyclic
combinational logic. Background equations and the completion expression are not
cuttable. All reductions are polynomial-time many-one reductions.

(a) Deciding Valid_H(K) for a supplied K is coNP-complete.

Membership: invalidity has a witness containing at most H+1 legal input blocks
and corresponding cut values, of length polynomial in the representation. A
deterministic evaluator checks the first disagreement in polynomial time.
Hardness: given a Boolean circuit phi(u), make a candidate wire c=0 and completion
D=c AND phi(u). The source completion is always zero. With K empty, the abstract
completion can be one exactly when phi is satisfiable: choose c=1 and a satisfying
u. Therefore Valid_0(empty) iff phi is unsatisfiable. QED.

(b) Deciding whether a supplied K is valid and inclusion-minimal is DP-complete,
where DP = {L1 intersection L2 : L1 in NP, L2 in coNP}.

Membership: validity is in coNP. By Theorem 3, all single deletions are invalid
exactly when each has a polynomial-length witness. There are at most |E| such
witnesses, so that conjunction is in NP. The empty retained set causes no
exception: its necessity condition is vacuously true.
Hardness: start with a pair of independent Boolean circuits phi(X), psi(Y), whose
required condition is phi UNSAT and psi SAT, the order-reversed SAT-UNSAT problem.
Make candidates c=0 and r=0 and completion

    D = (c AND phi(X)) OR (r AND psi(Y)).

The full source always has D=0. Choose K={r}. With r fixed at zero and c free,
K is valid iff phi is unsatisfiable. Deleting r frees both candidates; that
empty set is invalid iff phi or psi is satisfiable. Under phi UNSAT this is
exactly psi SAT. Thus K is valid and minimal iff the required UNSAT-and-SAT
condition holds. QED.

(c) Deciding whether there exists a valid K with |K| <= k is Sigma_2^P-complete.

Membership: existentially choose K and universally quantify bounded input/cut
behaviors; checking each resulting timing comparison is polynomial as above.
Hardness: start with an existential-universal Boolean circuit formula
exists x_1,...,x_n forall u: phi(x,u), with n>=1. A dummy unused existential bit
handles a formula with no existential bits. For each i, create candidate wires
a_i=0 and b_i=0. Set k=n and define

    D = OR_i(a_i AND b_i)
        OR ((AND_i(a_i XOR b_i)) AND NOT phi(a_1,...,a_n,u)).

The source D is identically zero. A valid retained set must keep at least one
wire from each pair: if both are omitted, havoc can make them both one, making
the first disjunct one regardless of all other values. The budget n therefore
forces exactly one retained wire per pair. Set x_i=0 when a_i is kept and x_i=1
when b_i is kept. A kept wire is zero. The first disjunct can no longer be one.
If any free counterpart is zero, the AND of XORs is zero and D is zero. Otherwise
all free counterparts are one, a_i=x_i for every i, and D equals NOT phi(x,u).
Hence this K is valid exactly when forall u phi(x,u). Every existential assignment
corresponds to one such K, proving the equivalence. QED.

Consequences. Absence of combinational cycles alone is not a polynomial-time
validity or minimum-size boundary unless the corresponding complexity classes
collapse. A separate structural restriction would need a separate argument.
These reductions refute a naive tractability premise; they do not assert that
these complexity classifications are historically new for slicing/core problems.
If every valid instance had a polynomial-size certificate checkable in polynomial
time in the circuit and certificate size, the coNP-complete validity language
would belong to NP, implying NP=coNP. Our explicit frontier checker makes no
such promise. In the H=0 hardness example, a single empty-state pair suffices as
a frontier, but checking it still enumerates all legal u and c valuations.

## 8. Concrete counterexamples and the first-hit comparison

Noncomposition of original-context omission proofs: let a=b=0 and D=a AND b.
Keeping just a is safe; keeping just b is safe. Keeping neither permits a=b=1
and is unsafe. Two individually justified omissions cannot be unioned without
checking their joint context.

Fixed-zero nonmonotonicity: let a=b=1 and D=a XOR b. The full source and the
program replacing both wires by zero both produce zero. Replacing just one wire
by zero produces one. Safety of fixed-zero replacement is therefore not monotone
in retained equations; it cannot justify Theorem 3's shortcut.

Inclusion versus cardinality: let a=b=c=0 and D=a AND (b OR c). Keeping {a} is
safe. Keeping {b,c} is also safe, and either deletion from that set is unsafe.
The greedy order a,b,c returns {b,c}, an inclusion-minimal set of size two,
although a size-one solution exists. This is an exact constructive gap, not a
statistical claim about the typical greedy result.

Shared value versus independent occurrences: let a=x and D=a XOR a. Omitting
the equation for a is safe under one shared havoc value. Independently assigning
its two expression occurrences would permit 0 XOR 1, which is a different and
strictly less precise abstraction. The prototype cuts definitions, not uses.

Old-state reads: a'=go, b'=a, D=b, initial a=b=0. With go=1 on the first sample,
b remains zero after the first update. Replacing b's old-state read with go (or
an already updated a) changes the completion timing. Tests must include retained
candidate equations; testing only all-cut contexts masks this error.

Post-completion fixture: phase is a two-bit register initialized to zero, updated
by phase'=phase+1 when phase<3 and phase'=phase otherwise. A one-bit flag records
the current input; a two-bit payload increments modulo four. Both initialize to
zero. Set H=4 and

    D = 1                           when phase=2,
        flag XOR payload[0]         when phase=3,
        0                           otherwise.

The source first completes at cycle 2 for every input. Retaining only the phase
next-state equation preserves this time under all cuts to flag and payload.
Omitting phase is unsafe, so the one-equation slice is inclusion-minimal. For
waveform equality, omitting flag or payload can change a later sample, and
omitting phase can change the first sample of completion; all three are needed.
The measured exact frontier counts are (1,16,16,0,0) for the first-hit slice and
(1,2,2,2,2) for the waveform slice. Total entries are 33 and 9, respectively;
preservation work is 338 and 32 observation/successor obligations. Less retained
state is not monotone in explicit proof size or checking work.

For a fixed retained set K, exact first-hit frontiers are subsets of the
waveform frontiers at each layer: stopping removes reachable continuations and
does not add any. This follows by induction on the common transition relation.
The comparison above changes K as well as the observer. A fixed-K diagnostic
retains all three equations under first-hit observation and gives frontiers
(1,2,2,0,0), five total entries, and 16 preservation obligations. Thus the stopping
rule reduces exploration at fixed K; the larger 33-entry first-hit certificate
arises from freeing flag and payload, not from stopping itself. This distinction
prevents a confounded attribution of cost to the observer.

The 16-way first-hit frontier has a simple explanation. After one update, the
original flag has two possible values; its original payload value is fixed by
the cycle. The abstract flag has two possible values and abstract payload has
four. Their independent choices give 2*2*4=16 pairs with a common fixed phase.
This persists at cycle 2, after which both complete and no pair is propagated.
The waveform model retains all equations, so both machines remain equal and
only the two possible flag values vary at each later layer.

## 9. Evidence and remaining trust boundary

The clean reproduction described in README.md regenerates 13 handcrafted
semantic controls and 96 Boolean-reduction instances. The generator, producer,
checker, and direct-oracle roles are separated in the implementation. The
checker uses a typed stack evaluator; the producer uses recursive expression
trees; the control oracle uses direct equations rather than either IR evaluator.
The finite checks cover all subsets of the 96 reduction instances, all 35
reported control necessity witnesses, and adversarial certificates including
replayable but nonleast witnesses. They do not enumerate every model accepted
by the IR, establish general parser or interpreter correctness, or replace the
mathematical arguments above.

The trusted boundary remains the supplied IR and its contract, the independent
checker implementation, both restricted source parsers, and the host runtime.
The producer is untrusted for acceptance. A restricted frontend and separate
instance validator are delivered for ten pinned public modules, but a general or
mechanically verified Verilog frontend, a verified checker, compact symbolic
proof certificates, and realistic accelerator evaluation are not delivered.
Novelty also requires comparison with the closest prior work; the supplied
finite checks alone do not establish it.
