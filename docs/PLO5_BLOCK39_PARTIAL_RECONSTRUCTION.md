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
