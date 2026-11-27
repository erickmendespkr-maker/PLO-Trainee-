# Macro14 — PPPoker candidate calibration and history strategy bridge
Base 9df65f1561dc4db0194ceb2adde71f52beb1a647. Offline post-session PLO5, branch feature/plo5-plo6-training only. No main writes. Local recovered subset, not full checkout; Windows and prior DNS blocker not retested.

## Bank recovery and labeled real video
Original calibration documentation docs/PLO5_BLOCK03_MIXED_SOFT_INTEGRATION.md says banks were distributed in local incremental packages, not committed. Searched current workspace, conversation/library and Drive (PLO_Trainee_bloco03) without locating original banks/packages. No real DriveHUD export located. Recovered original plo5_fourcolor_cards.py source exactly (blob 4b483c44527eaac5e30c7473c603ce576f7007e0). Reused original regions, rank masks, independent suit color, thresholds and training function; did not change thresholds. New provisional PPPoker bank trained from two visually labeled Parte01 frames (macro08_dev/frame_001.png, macro13_01/sample_00005.png), 30 hero cards and 12 board cards across 3 slots each, 42 masks across all 13 ranks. No raw screenshots committed. Bank SHA256 fb992caef5c4539486c74bca888a49f517c5ea9a2f7b1ba1439cd89397c8b95d, supplied only in local package calibration/ppp_bank.json, not in GitHub. Original PPPoker full and Suprema banks remain missing.

Separately visually labeled 6 selected Parte06 prints (macro13_06/sample_00001,02,03,04,09,10). Three PPPoker tables per print. Hero 72 correct / 18 unknown / 0 wrong, 90 slots; 6/18 complete exact hero holdings. Board including empty slots: 57 correct / 28 unknown / 0 wrong, 85 slots (exclude one animated board); 6/17 complete exact boards; 4/17 both hero and board correct. Same states repeat heavily; no general accuracy estimate, no independent annotator and no full-session truth. No calibration using Parte06. Initial hero-only bank produced same 72/18/0 hero totals; final bank adds board masks.
 
## Implementations
- 58012483cdd41af2ad8cad3e6208316e8a34011c, f84e23f70be4e8990d58f5cc605f62bb21a9d581: strict reconciled HU history to current street model. Replay only public prefix for decision root; explicit street-root ranges and rake rules required. No opponent revealed cards, future board or realized payout used as model input. Full record is validated before selection, but no general claim of strategy quality. Reject preflop, incomplete, unsupported side-pot/multiway cases and unmodeled inputs. Existing postflop/native solver/cache, optional persistent rank worker, HTML CLI.
- f2c9afa9d1987acfc752d28945936f8176e0a756, f39624fb98631d810c337ec93f7898d3bac77e03: original PPPoker classifier wrapper, bounded exact-pixel slot cache, bank validation and inactive slot roster test.
- 197b34f5c053061b433d60f3b995b123d5fd8b08, 05aa31e0de360a344ad7c1e3d1d05e763938dcc9, 2509ae1dda9693f7b03096f5a6dafbe9f6232f59: optional card reader in audited RGB stream, selective first-segment PNG alongside money changes, report with expandable board timeline/first screenshot, bank hash check. Still candidate segments, no confirmed actions or outcomes.
- a6bccd108cd8a5caea31ae5addd1d922116b6a96, c9031abd5190ad1a2ddf71202b3435c881c8a570: updated prior report regression for extra embedded segment image (two unique crops, three image references), opt-in GUI checkbox for bundled experimental bank.
- 146c2eaffe5ed09b23cfa31ddeedbb071725f972, 73766aaad428bd7347afa309cb0450f629dcc6a5, 944c5bdf14764d05d99aa00f2a3310b875ca3f76: documentation and synthetic history strategy example.

Local and remote tested code hashes matched:
 fc2f3f4182f56ef9912cfc2888ff7853b9b4a0be plo5_history_strategy.py
 7886c9bd03dd06466b8631acece3590f0de26f1f test_plo5_history_strategy.py
 fecf3cb5db20cb1a4c900d4e883cf97f3ae22524 plo5_ppp_card_reader.py
 7ce7843b26ca315557edb99053640ea7ac8d8631 test_plo5_ppp_card_reader.py
 05ecde215bc1d0ab68ed32579b4c77855235e99d plo5_video_stream.py
 905c49ed83678066dcbc2ef66e6233b6483954eb plo5_mvp.py
 623de315bbd0d048206b68e9d41f09f37fdf783f plo5_review_session.py
 d19a99f7450e614ad65f1e5b47807699fcfd98ba test_plo5_review_session.py
 b92883af1d02db83bb13c948abf0ccbd1d032ecc plo5_mvp_gui.py
 0466ab96f2db66eeee678e9a7fbd58898f839be6 packaging/LEIA-ME.txt
 0a3cbe1da60256bb6777f94c10b9384a588dc733 examples/history_strategy.txt
 22a60517c8acb46068dba19623c68b4644a87cae examples/history_strategy.json

## Actual runs
Recovered subset 150 tests in 27.436s OK, with PLO5_CFR_EXE, PLO5_MULTISTREET_EXE, PLO5_MULTIWAY_EXE, PLO5_INDEX_EXE, PLO5_RANK_EXE, PLO5_RANK_CATALOG, PLO5_RANK_WORKER_EXE set as Macro13. 145 prior + 5 new. First full regression failed one old image-reference count assertion; updated to verify new segment section and reran. compileall succeeded before last GUI/test changes; GUI Xvfb smoke passed, extracted package smoke passed. Native text example at river 100 iterations with explicit 2-pair range, pot odds 25%, native rank worker and HTML completed. Test verifies future river change leaves flop model identical. No actual DriveHUD record.

Parte01 [1530,1550): 20 frames, 3 card segments, 4 unresolved changes, 485/115 slot cache hits/misses, 6.46s / 119352 KiB (before final segment HTML change). Parte06 [620,640) final integrated report: 20 frames, 1 segment of 6 adjacent complete candidate observations (table 1), 4 unresolved changes, 6 selected PNGs, 8 unique table crops, 493/107 cache hits/misses, 6.12s / 125180 KiB. Source/PTS/RGB checked by existing integrated pipeline. Timing includes card recognition and report; not a controlled comparative benchmark. No verified complete real hand or confirmed position/action/showdown/rebuy. Changes may disappear across uncertain card continuity; no loss inference. No private media or raw screenshots published.

## Package and remaining
PLO_Trainee_Macro14_Candidato_Fontes.zip 194625 bytes, 113 entries, SHA256 f1030dd5d3b5d0c5a8d14b8e52ebd89f1f700ea3bbea526585e1a1e291f15f5e. Verified ZIP and 112 individual file hashes after clean extraction. Executed history strategy CLI with Python backend from clean extracted package; native CLI tested in development directory. Tk smoke passed. Contains provisional derived rank masks, no original video/frames or executables. Windows scripts unchanged and untested. No self-contained installer or certified MVP.
Remaining P0: complete real hand identity, all-seat stacks, seat/dealer positions, action sequence, payout/rebuy verification; original banks or independently labeled wider PPPoker/Suprema calibration; real DriveHUD export and supported grammar; explicit range provenance and wider solver coverage, Windows and long-session speed. Original automation branch and main unchanged by this cycle. Do not label candidate as complete. 
