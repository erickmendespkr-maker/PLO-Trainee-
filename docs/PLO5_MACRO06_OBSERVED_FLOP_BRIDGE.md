# Macro06 — Observed HU flop bridge
Base d2fb3b6a134bdbd2947ad00df8990fa8a7b4f89d. PLO5 offline post-session only, feature/plo5-plo6-training. Prior Macro05 deliverables confirmed in GitHub history. main unchanged.

## Delivered
34870f7bfd517c309c3ba059eee8116c38771645 — plo5_pre_post_bridge.py: replay strict preflop context, require a settled heads-up flop transition with both seats active and positive stacks, condition product-weight disjoint prior by explicit observed-action likelihoods, then by observed flop. Preserve exact rational joint probabilities and convert to bounded integer weights or reject; map preflop SB/BB order to postflop BB/SB. Transfer pot, remaining stacks, BB, rake and fold rule; explicit joint distribution is authoritative (marginal rows only declare support). SHA-256 keys bind history, likelihoods and observed board. Solve through existing multiway engine with conditional EV export; subtract preflop paid once to express net utility from hand start.
af56a90d5f745222836526f889b21b3f98cb123f — five regression methods for replay, exact probabilities, card blockers, fail-closed conditions, identity and end-to-end EV conservation/reconstruction.

## Verification
Direct git ls-remote failed DNS, exit 128. Recovered exact preflop tree and checked git hash-object:
a3a2b8ee5c5b4ce7b049c6956fc09e0fce1baafd plo5_pre_gto_tree.py (selftest passed)
d9e53867ace6f77ee8c5fc782b86e1f87d4bc194 plo5_pre_gto_context.py
32d4463d95f9b7e4de1e04370c95a24a52362788 plo5_post_gto_multiway.py
Published new blobs matched local executed files:
4d7099f48a3f45cea174274b719501fe2052d213 plo5_pre_post_bridge.py
84d6b4c7078e79bf8022f8ec67f3d21d27423f44 test_plo5_pre_post_bridge.py

From /mnt/data/plo5_05b/video_analyzer:
    PLO5_MULTIWAY_EXE=../native/multiway python -m unittest -v test_plo5_pre_post_bridge
    Ran 5 tests in 1.352s
    OK
    PLO5_CFR_EXE=../native/cli PLO5_MULTISTREET_EXE=../native/multistreet PLO5_MULTIWAY_EXE=../native/multiway python -W error::ResourceWarning -m unittest discover -q
    Ran 69 tests in 18.563s
    OK
    python -m compileall -q .
    exit 0

Synthetic fixture SB/BB initial stacks 4 chips, blinds 1/2, limp/check, two compatible weighted pairs. Observed history probability 1/3, posterior weights 1:1; a flop unblocked by both pairs has conditional probability 1/C(42,3); a flop blocking one equally weighted pair has half that probability. End-to-end native solve at one iteration; net EV sums to zero without rake and weighted conditional EV reproduces root EV. This is a consistency test, not strategy convergence or an independent ranking oracle.

## Limits / next
HU only, no prior folds/side pots/antes/straddles. Explicit action likelihoods are caller-supplied and not verified against actual opponent policy. No live analysis. Observed-flop solve is not all-flop preflop continuation and must not be used as fixed leaf values for an unrelated preflop reach. Need adapt verified preflop policy exports, full public chance and integrated preflop strategy training under budgets, multiway prior folds, cache/provenance, stronger convergence and deep-stack tests. Preserve prior Windows, full checkout/regression, video and room-specific rake backlogs.
