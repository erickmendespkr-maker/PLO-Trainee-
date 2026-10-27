# Cycle 138 — Real Monte Carlo through offline MP4 export

Scope: `docs/VIDEO_ANALYZER_SCOPE.md`. No playable tables, poker client
integration, live assistance, production changes, secrets, or paid services.

## Changes

- Added `test_offline_reviewed_pipeline_real_mc.py`: eight synthetic integration
  tests invoke the **real** `range_ev.py` / `equity.py` Monte Carlo engine through
  `offline_reviewed_pipeline.py`, the conditional EV bridge, and FFmpeg MP4
  export. No mathematical mock/stub is used in these tests.
- `offline_reviewed_math_clip_export.py` now rejects reports whose reported
  equity disagrees with `(wins + ties/2) / trials`. This is a consistency check,
  **not** independent verification of the poker simulation or input observations.
- Both PLO5 and PLO6 (fourth table) export a synthetic H.264 MP4 with a
  `mov_text` subtitle track and JSON hashes. Additional tests cover
  deterministic seeds, opponent card collisions, zero-weight ranges,
  unresolved manual reviews, unapproved clip exports, and tampered counts.

## Local verification

```bash
cd video_analyzer
python -m unittest discover -p 'test_offline_*.py' -v
```

Result in the local isolated test workspace: **131 selected tests passed**,
including **8 new tests**, on Python 3.13 with FFmpeg installed. The copies of
`range_ev.py`, `equity.py`, and `hand_history.py` used locally were
confirmed byte-for-byte against their branch Git blob SHA values. The
complete repository suite and remote CI were **not** executed.

Synthetic demonstration with 100 trials, seed 42, declared single-combo range,
pot 100, call 40, rake 0:

| Variant | Table | Wins | Ties | Losses | Equity | EV call |
|---|---:|---:|---:|---:|---:|---:|
| PLO5 | 2 | 90 | 0 | 10 | 90% | +86 chips |
| PLO6 | 4 | 92 | 0 | 8 | 92% | +88.8 chips |

These numbers are **not** observations from a real poker recording, and do not
prove a strategic error. Monte Carlo intervals quantify sampling uncertainty
only; ranges, OCR, opponent behavior, and timestamps remain unverified.
The short synthetic tests do not establish performance for four simultaneous
tables or 40–60-minute recordings.

## Blocker / next cycle

An authorized 3–5-minute recording with human annotations is still missing.
Continue with timestamp-to-decision provenance, multi-table synthetic
segmentation, and bounded long-video performance tests. Preserve explicit
manual approval and all uncertainty flags.
