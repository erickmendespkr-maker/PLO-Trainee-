# Macro06 — Policy bridge and public flop chance
Base 6cd27fac3ed9a9f14c26a0979d8621afc10c45ff. Offline PLO5 only. Branch feature/plo5-plo6-training; no main writes. Recovered Linux subset, not full repository.

## Delivered
- e59f693671fde5173be93d8df44ad39a6608c174: opt-in bounded posterior integer weights; exact mode default. Reserve positive weight for each supported deal and largest-remainder allocation across 10^12 units if exact representation exceeds budget. Exact total variation reported and must not exceed 10^-6. In native synthetic fixture actual TV 6.667366666666667e-13. This is a prior approximation bound, not a bound on solved strategy quality.
- 87219bcc755730ac446da0564766f9300a70727f: parse existing HU v4 indexed and multiway v4 physical policy export formats, validate observed public path against legal tree and per-holding action vectors, validate declared multiway rake, classify RFI/iso, 3bet/4bet, blind call/fold defense and all-in. Index mapping assumes sorted normalized input ranges, as existing HU prepare does. Source artifact hash recorded; training prior/context not independently verified. No claim that an arbitrary raw export corresponds to provided context.
- 2e5b49f3f239752eaf9bbf0d433918cffe218243: five tests including native-to-native training with synthetic equity matrix, bounded weight conversion, replay and betting classifications. Initial test assumed exact 1/6 from decimal-rounded float 1/3; adjusted comparison to 15 decimal places. Rake config keys verified against original rules module (bps,cap,on_fold).
- 9a684c09e2781fdf6a452b1cf711e6afc9ecc332: exact marginal flop chance conditional on modeled history, stream pair-board combinations into public-board aggregation; 11480 unordered flops per legal pair, bounded work. No continuation solving.
- 3b73caaca9e8e8005cd22cee3a26e3756f7247d2: three tests, mass, blockers, observed-flop bridge consistency and budget.

All five code/test hashes match tested local blobs:
33e1c3bcd56b50fcb1bd18d66929448cb6d89b0c plo5_pre_post_bridge.py
59ece5790ed2ac4ebe221b9728a8ef98d6d105ae plo5_pre_policy_bridge.py
d6b0f8e1378d040686c4b631a330b084c0c53e4e test_plo5_pre_policy_bridge.py
ca1f3abe8f1acc3afad7ed2ca4d9f7d0a75e275a plo5_pre_flop_chance.py
7599d4c550cca6baa8a62160f05ace0270bbe49f test_plo5_pre_flop_chance.py

## Local execution
From /mnt/data/plo5_05b/video_analyzer:
    PLO5_CFR_EXE=../native/cli PLO5_MULTISTREET_EXE=../native/multistreet PLO5_MULTIWAY_EXE=../native/multiway python -W error::ResourceWarning -m unittest discover -q
    Ran 77 tests in 20.736s
    OK
    python -m compileall -q .
    exit 0
Three additional chance tests passed in 0.167s separately. Bridge fixture has two compatible HU pairs, modeled limp/check path; 22960 physical pair-flop outcomes, 15190 distinct public boards, exact sum one. Native preflop test constructs compatible v4-format export using original preflop tree and native CFR adapter with explicitly synthetic equity values; not execution of full original HU prepare/solve pipeline. Native postflop solve uses observed flop and one iteration. No convergence claim.

## Next and limitations
Macro06 still partial: verified training-context provenance for indexed export, actual original preflop solver full integration/regression (recover dependencies), complete preflop strategy with public chance and continuation, 2–6-player pre-root folded blockers/side pots, full sizing trees and broad weighted ranges. A single observed flop EV must not be inserted into unrelated preflop leaves. Macro07 database expansion can proceed independently with provenance, versioned sparse artifacts and canonical physical keys, but no claim that complete solver strategy database exists. Preserve all prior backlogs, full checkout, Windows, room rules, video validation. No actual full checkout attempted in this cycle; previously documented DNS blocker not revalidated. No GTO or profit certification.
