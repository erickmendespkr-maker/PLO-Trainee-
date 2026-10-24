# Cycle 73 — Conservative consistency-to-frame review

Scope: `docs/VIDEO_ANALYZER_SCOPE.md`; recorded PLO5/PLO6 video only, offline/asynchronous. No live play, simulator, real-money integrations, or automated strategic verdicts.

## Added

- `activity_consistency_frame_review.py`: joins *human-reviewed* timeline consistency flags to uncalibrated ROI pixel-change intervals, using the existing temporal crosswalk.
- Requires an **explicit human PTS alignment declaration** before suggesting any frames; never guesses synchronization.
- Matches **same table, same human-assigned hand, same ROI field** and a time interval spanning the flagged and prior observations. Ambiguous multiple-hand matches are excluded.
- Keeps candidate frame paths, pixel review rank, PTS bounds, SHA-256 provenance, and review-only statuses; limits suggestions per flag and reports omissions.
- Refuses unsafe upstream authority flags, incompatible recording hashes, invalid budgets, and output overwrites.
- `test_activity_consistency_frame_review.py`: synthetic cases for alignment, four-table separation, ambiguous hands, field mismatch, timestamp offsets, deterministic budget, SHA mismatch, no mutation, and CLI.

## How to run

```bash
python -m pytest -q test_activity_consistency_frame_review.py test_activity_timeline_consistency_audit.py test_activity_visual_timeline_crosswalk.py
python activity_consistency_frame_review.py queue.json timeline.json frame_review.json --alignment-json alignment.json --max-frames-per-flag 5
```

Omit `--alignment-json` to produce an intentionally **unmatched** review report. The alignment declaration follows `activity_visual_timeline_crosswalk.py` and must be human-reviewed. The source images are *referenced*, not independently decoded or validated by this module; re-open them before approving any observations.

## Verified locally (2026-10-24)

- 29 selected tests passed, 14 subtests passed.
- 129 selected integration tests passed, 117 subtests passed.
- Full suite was started but did not complete within the execution limit; no full-suite pass claimed.
- Synthetic four-table fixture produced one board inconsistency and one same-hand ROI suggestion only with declared alignment. No poker action/EV or hand reconstruction was confirmed.

## Remaining blockers

No authorized real PLO5/PLO6 sample recording; recognition accuracy, actual hand boundaries, OCR and 40–60 minute throughput are **not verified**. No remote CI result claimed.
