# Macro13 — Text replay and release gates
Base ef4ce184650a885d86c81c1b9800a971b273f8c8. Branch feature/plo5-plo6-training only, no main writes. Recovered Linux subset, not full checkout. Prior DNS blocker not retested.

## Delivered
- 66824bf80ed23a44b02234e0c18aded404517089: strict PokerStars-style USD PLO5 text replay, 2–6 seats, standard blinds, button-to-position mapping, exact integer cents, raise-to conversion, all-in checks, ordered public cards, existing legal replay and gross zero-rake showdown evaluator, uncalled returns, observed gross pot/rake/payout conservation and per-seat gross award upper bounds. Rake allocation per pot not verified, side-pot payout labels not independently validated, no odd-chip rule, no incomplete/mucked active showdown support. Net result is conditional on the text, no independent source truth. Raw hero call pot odds are gross, not side-pot/rake adjusted. No inferred rebuy or strategy.
- def5e6cf27856acba993a42632082fcb010f2772: six tests (fold, all-in, complete tied showdown with rake, 3-player side pot, report, seven corrupt inputs). Synthetic fixtures only.
- c101a6bb8737336a72bb7add28f0a08d4015d052: existing history-mode HTML reports now show reconciled net BB, position, board, recorded rake and expandable hero decision pot odds, with unresolved records visibly rejected. No EV without a range model.
- 8eab71f28cfdcbf2450f61733e55b2d6935a98a5 and c17cee7eea3484113e288fa62f36fd4c1595b671: updated candidate readme and two complete synthetic history examples.
Verified remote blob matches local: 50c37e8492ab1b82eff22eac998a7c2dee923d4f history replay, c17b5aa7e50e33ca2666be91ab6f8594da707122 tests, f53d4329ca14927e9077f0be79e2e898bccf0cce intake, 9e2af8594ea08308fa2e00f5c5f501b20f9b8fcf readme, d7ee0020313f08f93f3f637f45ed5545419fb6a1 example.

## Execution
From /mnt/data/plo5_05b/video_analyzer with prior native binaries and catalog:
 PYTHONPATH=.. PLO5_CFR_EXE=../native/cli PLO5_MULTISTREET_EXE=../native/multistreet PLO5_MULTIWAY_EXE=../native/multiway PLO5_INDEX_EXE=../native/index_batch PLO5_RANK_EXE=../native/rank_batch PLO5_RANK_CATALOG=../rank_macro07/rank_catalog.json PLO5_RANK_WORKER_EXE=../native/rank_worker python -W error::ResourceWarning -m unittest discover -q
 Ran 145 tests in 27.306s
 OK
 compileall succeeded. 139 prior + 6 new. No Windows runtime or compiler present. No full repository regression.

New real-video windows using unchanged Macro12 integrated candidate:
|video|window seconds|frames|unresolved changes|selected PNGs|wall s|peak KiB|
|01|1530–1550|20|5|9|6.27|126808|
|06|620–640|20|4|6|5.46|123028|
Both source hashes matched earlier recordings. Direct RGB + selective re-extraction matched each frame's RGB and exact PTS in workflow; no independent accuracy labels. 133/27 and 96/24 cache hits/misses. No verified real hand, no new video recognizer optimization; smoke of existing pipeline, not a comparative benchmark. Reports private, not published. No full-session speed claim.

## Package
PLO_Trainee_Macro13_Candidato_Fontes.zip 178901 bytes, 105 entries, SHA256 5c46db1ba4b57a755ae971379ea00c03c37d2db62f4445a646cf79433c7872e7. Derived from Macro12 file roster plus two Python modules and example; hash manifest for 104 files, ZIP test and fresh extraction passed. Extracted source CLI history produced 2 consistent text replays, zero rejected, report; preflight all dependencies present in Linux; xvfb-run GUI smoke passed. No binaries or private recordings included. Existing Windows preparation scripts unchanged; not a Windows installer or certified MVP.

## Release blockers
No real DriveHUD export in local inputs, no parser validation for original PPPoker/Suprema exports. Need user export sample if not retrievable. Next priority: actual export grammar and full per-hand parser (mucked losers and side-pot eligibility/rake/odd chips), bridge decision prefixes with explicit verified ranges without using future showdown cards. Real-video card/action/seat bank recovery and calibration, verified hand identity, settlement/rebuy and strategy evidence gate still required. Windows runtime/installer, realistic session throughput, solver range coverage and all earlier pending work preserved. Do not describe this candidate as finished.