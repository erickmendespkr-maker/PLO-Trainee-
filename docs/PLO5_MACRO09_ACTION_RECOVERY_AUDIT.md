# Macro09 — supplementary recovery and evidence audit
Offline post-session PLO5 only. Branch feature/plo5-plo6-training. Initial HEAD 33a39926ff31abc7729b60f90e5bb4099b492781. No main writes by this cycle.
Recovered local modules plo5_reconstruct_ledger.py and plo5_reconstruction_candidates.py and associated tests; confirmed subsequent publication by rereading branch (attempt to create ledger returned 422 because another execution already published identical blob). No overwrite of those files. Ledger replay uses declared full history, chip payments, card reveals, standard blinds, all-in/fold/showdown, main/side pots, exact fractional awards, rake and explicit separate external rebuy. No video truth certification. Candidate collector preserves gaps and unresolved display changes, never turns money deltas into verified net EV.
New implementation plo5_action_recovery.py plus tests: e6fa5c891787a660df99841b1c363328b0326d2a, 29dd3b14f0c4180cd1d97aeda67b8f816fbaf4cf; next-actor and street-closure constraints in ebf7fa8432e67b5156dc7177dacdd8883d4f7c51 and 495504f19694ecc28fcdd9131fd5bb53d54452c6. Full per-seat snapshot in integer chips; legal pre/post tree, monotonic contributions and pot conservation; optional folded roster, expected actor (including no pending actor) and expected status; exhaustive legal integer raises within declared max_actions and max_nodes. At most two paths suffice to prove ambiguity; truncation not uniqueness. Does not search across street transitions, payouts or rebuys. No action/financial/strategy authorization. Seven direct tests (call/check ambiguity, fold, raise, budget, next actor, street closure, postflop).
Concurrent execution also published plo5_action_reconstruct.py with analogous infer API and four tests. Consolidate the two APIs after reviewing consumers; both preserved here rather than overwrite a parallel change. HEAD d9b15a91e1d7e2cfadc0abe4ef3fa5d56c602e55 observed before this addendum.
Tested local blob hashes:
 a05e933b6fa1993f5952d63b2546dabfb8e9ebad plo5_action_recovery.py
 940b8bf77a830cdd8bc4428f057a94be01ea3fd2 test_plo5_action_recovery.py
 11b94b46278d2d3942dfa4d10c21a0eeb3550e97 plo5_reconstruct_ledger.py
 e084a8177d635a914703e0eaf9e74979b7a49454 test_plo5_reconstruct_ledger.py
 ed657b932d6526ffb4d62dbd41aadc3f584ab65f plo5_reconstruction_candidates.py
 0596aacf558c41bba95f6a3d6134902647a1b627 test_plo5_reconstruction_candidates.py
Local recovered subset, not full checkout:
 PYTHONPATH=.. PLO5_CFR_EXE=../native/cli PLO5_MULTISTREET_EXE=../native/multistreet PLO5_MULTIWAY_EXE=../native/multiway PLO5_INDEX_EXE=../native/index_batch PLO5_RANK_EXE=../native/rank_batch PLO5_RANK_CATALOG=../rank_macro07/rank_catalog.json python -W error::ResourceWarning -m unittest discover -q
 Ran 118 tests in 22.835s
 OK
 python -m compileall -q . exit 0
98 prior + 20 additional methods, including four parallel infer tests. Prior DNS not retested. No Windows certification.

## Real video evidence independently repeated
Local source hashes: Poker_Parte_01.mp4 c9aad5102a54941b8cb5f4bbc20eca45fc757ff96fd95de173c0ac0d95ac19eb; Poker_Parte_06.mp4 fef7af4d59388f254f3c72efbf0a9127acacc42e9115c4d198a7277b18ae46a2.
Two local pre-existing manifests (macro09_01, macro09_06). Recomputed all source hashes, checked each exact rational PTS against ffprobe best_effort_timestamp * time_base, independently re-extracted the same windows from source via original mixed_review select/showinfo PNG settings. All 40 PNG SHA-256 hashes and all 40 PTS matched. Re-read each verified image via MixedReader without manual bank, exact observation equality to manifests; collect result identical to existing candidates.json. Readings are candidates, no independent human truth labels. No private video or image committed.
| Video | Window | Frames | Active slot count | Amount reads | Non-null | Display changes | Card segments |
|---|---|---:|---|---:|---:|---:|---:|
|01|1510–1530 s|20|4 on all 20|160|154|9|0|
|06|600–620 s|20|2 on 3, 3 on 17|114|114|4|0|
Re-read timing (PNG loading, MixedReader, collect; excludes extraction): 2.529 s / 1.336 s. Cache hits/misses 117/43 and 98/16. No independent precision metric, no full hand reconstructed, no financial result certified, no session throughput claim. Part06 now used for independent source/window test, not training bank; still no labeled holdout accuracy test.
## Remaining
Recover real calibrated card banks and integrate/validate full mixed-video CLI; recognize all seats' stacks, actions, dealer/positions, highlighted showdown; validate source changes, missing actions and actual settlement/auto-rebuy with independent reference. Dynamic slots only, arbitrary resizing unvalidated. Consolidate duplicate action recovery APIs; bridge verified evidence to strategy only with complete inputs and confidence gates. Full checkout/Windows, room rake, prior solver/database and performance backlogs remain. Macro09 partial; Macro10 may start on explicitly validated structured review inputs, not unverified video guesses. No full MVP or GTO claim.
