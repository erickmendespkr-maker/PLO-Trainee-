# Cycle 149 — reviewed OCR to incomplete hand candidates (2026-10-27)

Scope: `docs/VIDEO_ANALYZER_SCOPE.md`; offline PLO5/PLO6 recordings only. No live poker, playable tables, opponent AI, credentials, paid services, GitHub Actions, or main changes.

## Delivered

- `offline_four_table_hand_candidates.py`: groups *human-reviewed* OCR observations into human-declared hand windows (1–4 tables, PLO5/PLO6). Every observation retains source PTS, crop SHA-256, review decision and field value.
- Revalidates the original sample bundle and recording hash, original OCR report and human review manifest by rerunning the previous review validator. Compares the entire reviewed report and its byte-level hash before grouping.
- Enforces create-only output, exact input hashes, explicit visual boundary review, unique hand IDs, ordered non-overlapping windows per table, bounded and unique observation indices, same-table observations and source timestamps inside each window. Rejects rejected/unreviewed observations, unexpected fields, invalid windows and tampered crops.
- Emits missing observed fields, changing board/hero card values and same-PTS hero/board card collisions as *review flags*, not conclusions. Every candidate remains incomplete, with equity/EV and automatic clip selection disabled.
- `test_offline_four_table_hand_candidates.py`: 25 self-contained synthetic tests using FFmpeg, Tesseract, OCR review and provenance checks.

## Verified locally

- 25 new tests pass; 129 selected tests pass including 104 earlier region extraction, OCR, visual-change and segmentation regression tests. No tests skipped in the selected suite.
- Demonstration with a synthetic 60-second four-region recording: 2 incomplete hand candidates, one per selected table; no math promotion. This demonstrates grouping only, not genuine poker-hand reconstruction.
- Git blob hashes of published module and tests match the local files used for testing.

## Not verified / blockers

- No real annotated PLO5/PLO6 video (3–5 minutes recommended); no measured recognition precision.
- No complete action history, opponent ranges, equity or EV from video. A visually checked window is not independently authenticated.
- No full repository suite, CI run or 40–60 minute four-table throughput benchmark.

## Example

`python video_analyzer/offline_four_table_hand_candidates.py samples/ ocr_proposals.json review_manifest.json reviewed_fields.json hand_windows.json hand_candidates.json --recording session.mp4`

Hand windows JSON schema: `schema_version:1`, `source_reviewed_fields_sha256`, `hands` array with `hand_id`, `table_id`, `game_type` (`PLO5` or `PLO6`), `start_pts_seconds`, `end_pts_seconds`, `boundaries_visually_checked:true`, `observation_indices` (indices into reviewed OCR candidates). The output is always `ready_for_equity_or_ev:false`.
