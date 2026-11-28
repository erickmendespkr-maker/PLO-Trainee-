# PLO5 Block 39 — bounded checkpoint recovery and legal-prefix replay (partial)

Date: 2026-11-28. Development branch only: `feature/plo5-plo6-training`.
Starting HEAD: `c4f54314f10007c76f669a961584bf4bf67a047a`.
Code HEAD before this note: `33091b9c69eb00801a6593fae002bfb439618049`.
Main observed unchanged: `d61417489da92a9535cd84c3a23c69f975e7056f`.

## Concrete changes

- `plo5_observation_checkpoints.py`: combine *identical* unresolved observations by preserving their first timestamp. Preserve distinct stacks, pot, active players and actor constraints. Enforce six distinct-checkpoint budget and an independent pending-time limit.
- `plo5_auto_reconstruct.py`: apply this bounded compaction to incomplete observations and ambiguous legal intervals. New conservative closure reasons `CHECKPOINT_TIMEOUT` and `CHECKPOINT_LIMIT`; count `DEFERRED_DUPLICATE`.
- `plo5_replay_audit.py`: replay candidate action and community-card events from the original posted-blind seed using existing pre/post engines and `plo5_snapshot_replay.reveal`. Reject illegal actions, skipped streets, private/community duplicates and inconsistent terminal state. This is a legal-prefix audit **not** independent video truth.
- `plo5_auto_reconstruct.py`: run legal-prefix replay on candidate closure, attach `replay_audit`, and suppress decision records on replay mismatch (`REPLAY_AUDIT_REJECTED`). Keep `hand_verified=False` and all strategy/financial authorization flags false.
- New tests `test_plo5_observation_checkpoints.py` (7 methods), `test_plo5_replay_audit.py` (7 methods), plus 3 regression methods in `test_plo5_auto_reconstruct.py`.

## Tests actually executed in the chat Linux sandbox

- 7/7 checkpoint-unit tests passed, with the exact helper implementation.
- 6/6 isolated replay-audit tests passed **using mocked betting/dependency modules**. These test input validation and replay-result handling, not actual PLO5 pre/post parity.
- 6/6 earlier visual-continuity isolated tests also passed.
- Python compilation passed for the new helper and replay-audit source.
- These are 19 isolated tests, **not** full repository regression. The 7 full-engine replay-audit tests and 3 new auto-reconstruction integration tests were committed but were **not run** in the full repository in this session.

## Evidence recovery / blockers

- GitHub branch HEAD verified with connector; GitHub Actions reported no checks or workflow runs for the code HEAD.
- `calibration/ppp_bank.json` and `calibration/suprema_bank.json` both returned GitHub 404. Drive searches for the named bank files and the old Macro32 integrated ZIP found no matching files.
- Google Drive metadata confirmed Parte01 (`Poker_Parte_01.mp4`, 167993622 bytes), but no video bytes were decoded and no hands from Parte01 were certified here.
- Linux DNS could not resolve `github.com`, `raw.githubusercontent.com`, or `api.github.com`. Repo content was retrieved and updated via the GitHub connector instead.
- Parte06 remains an untouched holdout; no observations, screenshots, video bytes or private hand evidence were committed.

## Still open before calling block 39 complete

1. Recover authentic calibration banks with provenance and verify hashes, or a valid prior-observation set from Parte01.
2. Execute all existing reconstruction and replay tests on a full checkout with real pre/post engines and resolve any regressions.
3. Run Parte01 and independently annotate/review real hand boundaries, actions, stacks and complete terminal hands.
4. Validate resulting legal replays, conservation and hand/decision denominators; no automatic certification flags until upstream evidence is defensible.
5. Preserve unresolved work from blocks 35-38; do not mistake isolated legal-prefix consistency for accurate OCR, complete hands, or +EV decisions.

Scope remains PLO5 offline post-session. Main untouched; DriveHUD on standby; no external AI or RTA. No scheduled automation requested for this execution.

## Follow-up: real-engine regression and Parte01 pre-calibration evidence (2026-11-28)

### Local source retrieval and tests

A partial checkout of **66 original repository Python modules/test files** was recovered through the GitHub connector (the Linux container still could not resolve github.com DNS). Modules were transferred via a temporary private Drive document to the local Linux sandbox solely for validation. The temporary bridge is not a source repository or a calibration bank.

The actual preflop, postflop, snapshot replay, financial bridge, auto reconstruction and integration modules executed together: `python -m unittest -q test_plo5_auto_reconstruct test_plo5_snapshot_replay test_plo5_replay_audit test_plo5_observation_checkpoints test_plo5_visual_continuity test_plo5_financial_bridge test_plo5_macro32 test_plo5_integrated_video test_plo5_post_gto_multiway test_plo5_post_gto_river`.

**Result: 77 tests, 70 passed, 7 skipped, 0 failures (Linux Python 3.13.5).** The skipped tests depend on authentic card calibration and/or an optional compiled native worker. This verifies a **targeted subset**, not 1,800+ repository entries or a full Windows release. Pillow emitted non-fatal `Image.getdata` deprecation warnings.

Previously published `test_partial_chain_stays_contiguous_without_losing_anchor` expected two checkpoints for identical pending observations. The new compaction deliberately retains one checkpoint and counts the duplicate. Corrected the test to require `['1']` and `DEFERRED_DUPLICATE==1` (commit `18cbd16720812bb9697436dba40cc1d8e46f212c`).

The Macro32 reanalysis integration test used the missing `calibration/ppp_bank.json` unconditionally when FFmpeg was installed; this caused `FileNotFoundError` in a clean environment and masked the available tests. The test now explicitly skips if that **authentic** bank is missing, without generating substitutes or certifying pipeline success (commit `74490321c819d71790a3789fdec0d125bebadcf2`). The skipped end-to-end portion remains **unvalidated**.

### Real Parte01 video checks (not certified hands)

The original file `Poker_Parte_01.mp4` was recovered from the user's private Drive to the local sandbox. FFprobe returned **1618.000 seconds**, file size **167,993,622 bytes**. SHA-256 `c9aad5102a54941b8cb5f4bbc20eca45fc757ff96fd95de173c0ac0d95ac19eb` matches the prior documented checksum.

With the existing `plo5_mixed_money.detect` implementation, OpenCV decoded **108 frames**, one every 15 seconds across Parte01, in **5.59 s** (excluding startup and transfer). Table-level candidate counts:

| Table | PPPoker | Suprema | Undetected |
| --- | ---: | ---: | ---: |
| 1 | 108 | 0 | 0 |
| 2 | 108 | 0 | 0 |
| 3 | 107 | 0 | 1 |
| 4 | 14 | 74 | 20 |

This verifies **layout detection on sampled real frames**, not a ground-truth classification accuracy measure or a complete hand reconstruction. Screenshots, stacks, cards, and timestamps are not published.

The existing `plo5_mixed_money.read` (Tesseract 5.5.0) was exercised for stack/pot OCR on six separate timestamps (**2, 20, 60, 300, 920, 1450 seconds**). Across active table/field pairs, 44 of **46** reads returned a numeric candidate, and 2 returned no numeric candidate (5.324 s wall-time for the six-frame batch). No comparison with human-reviewed values was performed: **44/46 is candidate availability, not accuracy**.

### Calibration recovery evidence and remaining blockers

`calibration/ppp_bank.json` and `calibration/suprema_bank.json` were absent from the complete GitHub tree (1,831 entries); Drive name searches did not return the bank files. The prior `PLO_Trainee_Macro32_Candidato_Integrado.zip` (375,098 bytes) and `PLO_Trainee_Macro22_Parte01_Manifestos.zip` (518,982 bytes) **were located in the user's Library**, but attempts to materialize their raw bytes failed with `This Project file does not have an authorized raw-byte materialization path.` Their internal calibration/observation files therefore have **not** been inspected or imported. Do not assert that those ZIP contents have been recovered.

A complete Parte01 observation → event → legal reconstruction → financial reconciliation pass still requires authentic calibration banks (or verified prior observations). No real complete hands or strategic mistakes were certified in this follow-up. Preserve Parte06 as untouched holdout. DriveHUD remains in standby; no automation or RTA.

### Additional reproducible preflight and combined regression

New `video_analyzer/plo5_video_preflight.py` provides a **bank-independent diagnostic**:

```bash
python video_analyzer/plo5_video_preflight.py Poker_Parte_01.mp4 --step 15 --samples 512 --ocr-samples 6
```

The command samples the MP4 with OpenCV, calls the existing `plo5_mixed_money.detect` and optionally its stack/pot `read`, and emits **aggregate counts only** (no timestamps, hole cards, amounts, screenshots or reports of individual hands). A false or absent OCR candidate stays unknown. It never sets hand, financial, or strategic certification flags.

Actual run on original Parte01: SHA-256 verified; 108 frames at 15-second intervals; detection counts exactly as in the table above; six evenly distributed OCR frames returned **23/24 numeric stack candidates** and **22/24 numeric pot candidates**. This differs from the separate manually selected six timestamps (44/46) above because the sampling times differ; neither measure is ground-truth accuracy.

`test_plo5_video_preflight.py` adds 4 tests (invalid budgets, missing MP4, synthetic black video with no false-positive layout or financial claims, invalid geometry). All 4 passed locally with real FFmpeg/OpenCV. The combined Linux command:

```bash
python -m unittest -q test_plo5_auto_reconstruct test_plo5_snapshot_replay test_plo5_replay_audit test_plo5_observation_checkpoints test_plo5_visual_continuity test_plo5_financial_bridge test_plo5_macro32 test_plo5_integrated_video test_plo5_post_gto_multiway test_plo5_post_gto_river test_plo5_video_preflight
```

**Result: 81 tests, 74 passed, 7 skipped, zero failures, 2.878s wall-time**, with actual original engines and selected tests recovered by GitHub. No authentic bank means no certified full-video reconstruction, no hand denominator and no financial +EV classification. Remaining blocker stays the authentic card-bank or validated observation set, followed by complete Parte01 and independent ground truth.


## Recovered Macro32/Macro22 authentic calibration and manifest archive (2026-11-28)

A later, successful **user Library → temporary private Google Drive copy → local Linux** transfer recovered the exact historical ZIP bytes. The Library originals were not modified.

| Source | SHA-256 | Integrity |
|---|---|---|
| `PLO_Trainee_Macro32_Candidato_Integrado.zip` | `cf0f34240593a46f6a3a3cfe6251cf9bc1b7328651ff1636d7fcd6f85ae29b36` | All 168 files in the built-in SHA256SUMS matched |
| `PLO_Trainee_Macro22_Parte01_Manifestos.zip` | `fd8eb6b0ee2d001b8c953cf59355db547ebe14f173e7da33b67a940edd3ca89d` | All 14 declared window SHA-256 hashes matched |
| `Poker_Parte_01.mp4` | `c9aad5102a54941b8cb5f4bbc20eca45fc757ff96fd95de173c0ac0d95ac19eb` | Source hash matches the archived session |

Three authentic rank-template files were restored to the **private development branch**:

- `calibration/ppp_bank.json` SHA-256 `fb992caef5c4539486c74bca888a49f517c5ea9a2f7b1ba1439cd89397c8b95d` (42 original rank templates)
- `calibration/ppp_macro18.json` SHA-256 `17ae09d9bb29ebd3b1c76e20f61047ad415a8eeaf74e5cd217d10f9f80a17c37` (102 templates)
- `calibration/suprema_bank.json` SHA-256 `9850343ce83bc569695491fe42b3eff2a4b178209a0188f86a0e114dc7654c02` (47 templates; from `calibration_complementar/suprema_macro18.json` in Macro32).

The Macro22 session explicitly declares the latter two SHA-256 hashes, PLO5, 14 windows, **1,604 sampled frames**, and `hands_reconstructed=false`. The original file-window bytes stay private and local; they are **not checked in**, nor are frames, player holdings, pot amounts, or individual session decisions. These hashes prove **file integrity and compatibility**, not visual-recognition accuracy.

`video_analyzer/plo5_manifest_archive.py` now imports the original Macro22 ZIP safely: exact MP4 and bank SHA-256 matching, template structural checks, file roster, timestamp ordering, per-window hashes, bounded decompression, atomic local restore, and zero verification claims. A malicious extra path or tampered window is rejected. `test_plo5_manifest_archive.py` adds seven tests.

Reproducible offline import (from the repository root):

```bash
python video_analyzer/plo5_manifest_archive.py Macro22_Parte01_Manifestos.zip Poker_Parte_01.mp4 observacoes_restauradas --ppp calibration/ppp_macro18.json --suprema calibration/suprema_bank.json
python video_analyzer/plo5_integrated_video.py Poker_Parte_01.mp4 saida_diagnostica --session observacoes_restauradas/session.json --start 0 --seconds 60 --tables 2 --workers 2 --ppp calibration/ppp_macro18.json --suprema calibration/suprema_bank.json --refine-budget 0
```

The restored `session.json` passed the **actual current** `plo5_bounded_session.load_interval` for intervals `0:12`, `113:9`, `149:31`, `812:22`, `1503:17` (seconds). A real `plo5_integrated_video` run processed seat/dealt evidence on Parte01 with the matched banks; no synthetic game observations were substituted.

**Conservative continuity improvement:** a complete, positive-identity, adjacent-PTS snapshot can remain visually unchanged for more than three seconds while a player thinks. The original ambiguity timeout prematurely closed actual candidates; ambiguous-complete snapshots now retain a bounded `min(30 seconds, 10 * max_gap)` grace interval, while incomplete observations keep their stricter existing timeout. The action-path and terminal-status audits, six distinct-checkpoint budget and absence of authorization remain unchanged. Two new tests cover continuation through a stable interval and an absolute timeout.

A local comparison on the *same* archived enriched observations found, for table 2 around 0–60 seconds, one candidate prefix grew from **1 to 4 legal candidate events** before a genuine `UNANCHORED_STREET` conflict. This is **not** evidence that four true actions were verified. The longer pending window retains evidence for disambiguation; it does not force or certify a hand.

**Extended Parte01 sample (real video, source-matched banks, original PLO5 engines):**

- Table 2: 0–116 seconds, 116 observed frames; 2 candidate prefixes, 0 decision candidates, 0 terminal/verified hands. Closures: one `UNANCHORED_STREET`, one `SESSION_END`.
- Table 1: 145–240 seconds, 95 observed frames; 2 candidate prefixes, **1 unverified** decision candidate, 0 terminal/verified hands. Closures: one `CHECKPOINT_TIMEOUT`, one `SESSION_END`.
- **Total: 211 decoded frames, 4 replay-consistent incomplete prefixes, 1 unverified decision, 0 financially certified hands.** Do not confuse prefix legality with ground-truth actions or rake/rebuy reconciliation.

The combined local regression was **90 tests, 87 passed, 3 skipped, 0 failures**. Skips depend on optional native functionality; authentic PPPoker calibration now makes the Macro32 integrated test runnable. A full Parte01 reconstruction and independent manual ground truth remains unresolved. No bankroll result, winner, 30-BB loss, showdown or +EV decision has been certified.

Keep main, the Parte06 holdout, DriveHUD standby and post-session/offline scope unchanged. No RTA and no automation.


## Follow-up: bounded river transition and payout uncertainty (2026-11-28)

Starting HEAD: \`e7cabfda5abea904fcb024fa332852244291337c\`. This round preserves the eight commits from that HEAD. \`main\` remains protected and Parte06 is not inspected.

### Actual code change: conservative boundary closure

\`plo5_auto_reconstruct.recover(..., required_status=...)\` now supports an optional betting-state terminal constraint. At an observed new community-card street, if the prior betting engine has pending actors, the reconstructor searches for a *unique* legal closed betting prefix whose pot, remaining stacks and prior deferred checkpoints match the observed screen, bounded by the existing maximum action/node budgets. Only then does it reveal community cards through \`plo5_snapshot_replay.reveal\` and append the inferred events. If the path is ambiguous, the pot does not conserve, or the actor/dealer/board mismatches, the hand remains \`UNANCHORED_STREET\`. Previously the reconstructor immediately rejected such changes even when a unique prior-street completion existed.

The new \`BOUNDARY_UNIQUE_WITHIN_BOUNDS\` and \`BOUNDARY_ACTIONS_UNVERIFIED\` counters distinguish successful **legal-prefix reconstruction** from verified screen actions. Inferred actions crossing a street boundary deliberately do **not** produce strategic decision or print requests, and the hand and finances remain unverified. This supports flop, turn and river, with three negative/positive unit tests plus a river-progression regression.

### Actual code change: missing-pot financial uncertainty

When a *partial* visual observation shows an increase in a known dealt seat's stack, it now closes with \`PAYOUT_OR_REBUY_UNRESOLVED\` rather than generic \`INCOMPLETE_OBSERVATION\`, even if the pot OCR is unavailable. Neither payout nor rebuy is attributed; the classifier only acknowledges an unexplained stack increase that is impossible to obtain through a betting action alone. A new test asserts the uncertainty status and forbids financial, hand or strategic certification.

### Actual original Parte01 comparison

All frames here were already OCR-enriched from the original \`Poker_Parte_01.mp4\` with restored Macro32 rank banks and verified Macro22 session. They were **not generated from fabricated observations**, and no frames/cards/amounts are included in this Git history.

For table 2, consecutive archived observations from 0–116 seconds (116 frames) were fed into a **single** \`ReconstructionStream\` across both previous 20-second segment boundaries, with final closure only after all frames. Comparing original \`e7cabfda...\` source vs updated source:

| Measure | Before | After |
| --- | --- | --- |
| First candidate end reason | \`UNANCHORED_STREET\` | \`PAYOUT_OR_REBUY_UNRESOLVED\` |
| First candidate events | 4 | 18 |
| Distinct public street transitions recovered | 0 | 2 |
| Additional unanchored legal betting actions | 0 | 4, explicitly unverified |
| Replay audit of the prefix | \`LEGAL_PREFIX_CONSISTENT\` | \`LEGAL_PREFIX_CONSISTENT\` |
| Certified hands / financial results | 0 / 0 | 0 / 0 |

A second candidate from 115 seconds remains unverified. The first sequence has a river board with incomplete terminal betting. Independent local half-second money OCR probes at 107.5–114.0 seconds found readable pot values before the payout animation, a sustained interval where pot OCR returned \`None\`, then a new posted-blind pot. This missing visual interval prevents assigning a pot, rake or rebuy with independent certainty. At table 1 around 207.5–213.0 seconds, a similar pot-OCR blackout was observed during a stack increase. Those are still **financially unresolved**, not verified winners or 30-BB losses.

At table 1, 180–240 seconds (60 existing OCR-enriched frames) yielded the same 5 legal-prefix candidate events before and after, one **unverified** decision candidate, and zero financially verified hands. No changes were forced where the additional boundary inference did not apply.

### Executed regression

The actual targeted test suite in Linux, using the original pre/post engines, authentic restored calibration banks and the source modules, was re-run **after both code changes**:

\`\`\`bash
cd video_analyzer
python -m unittest -q test_plo5_auto_reconstruct test_plo5_snapshot_replay \
  test_plo5_replay_audit test_plo5_observation_checkpoints \
  test_plo5_visual_continuity test_plo5_financial_bridge \
  test_plo5_macro32 test_plo5_integrated_video \
  test_plo5_post_gto_multiway test_plo5_post_gto_river \
  test_plo5_video_preflight test_plo5_manifest_archive
\`\`\`

**95 tests run: 93 passed, 2 skipped, zero failures** (Linux Python 3.13). The skipped cases require optional native dependencies. This is a targeted regression, not a full release/Windows test. No tests were run on Parte06.

### Still required

- Recover the final river/fold/showdown action from direct visual evidence where the pot is masked.
- Separate awards, rake and rebuy using independent before-and-after seat balances, not merely a rising stack.
- Compare uncertain OCR observations with manual source-video annotation before marking any complete hand, mistake or \`+EV\` result.
- Run more of the 26:58 Parte01 session and full Windows 10 low-memory performance tests.
- DriveHUD remains in standby; all operations are post-session/offline, no RTA, no automation.
