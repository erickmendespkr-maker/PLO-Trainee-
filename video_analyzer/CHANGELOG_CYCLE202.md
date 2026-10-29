# Cycle 202 — Offline four-table visual timeline (synthetic)

## Scope and design
Only `feature/plo5-plo6-training`; `docs/VIDEO_ANALYZER_SCOPE.md` governs this work. No playable tables, opponents, live poker, wagering, production services, credentials, or paid tools.

## Implemented
- New `offline_four_table_visual_timeline.py` accepts a **recorded local** MP4/WebM/MKV (up to 70 minutes) and uses FFprobe to validate duration/dimensions.
- FFmpeg samples decoded video frames approximately once per second (configurable 0.5–5s) and retains **selected source-frame PTS** via `select` + `showinfo`, without resetting PTS to a synthetic clock. A VFR synthetic test verifies noninteger timestamps.
- Fixed 1–4 table layouts (1 full frame, 2 columns, 3–4 in a 2×2 grid). For each ROI, calculates the proportion of grayscale pixels changing beyond an intensity threshold and groups activity into padded candidate intervals. Reports source-pixel and normalized ROIs, individual change-event PTS, all sample PTS, source-video SHA-256, and confidence **limitations**.
- Explicitly labels all candidates as **visual activity only**: not confirmed hands, OCR, cards, actions, player identities, equity or EV. This module is a temporal prefilter for later human/OCR review, not a hand reconstruction engine.
- Output JSON is created exclusively as a new file. The input file is hashed before and after decoding; no original video modification.

## Verified in local container
- 20 new unittest cases passed, including 4 independent quadrants, 1/2/3 table geometry, grouping, PTS mapping, a variable-timestamp source, invalid input and output overwrite protection.
- Combined selected regression suite: **130/130** passed (110 existing tests from the prior cycle's local source bundle + 20 new tests).
- Synthetic 12-second 4-table video: four changes independently detected at source PTS **2, 4, 6, 8 seconds**.
- Synthetic **60-minute, 1-fps, 320×192** video: 3,600 sampled frames, four independent events at source PTS **600, 1200, 1800, 2400 seconds**, 4 candidate windows. In this container, generation took **1.37 s** (36,608 KB peak), and analysis **5.16 s** (209,552 KB peak), as measured by `/usr/bin/time`; these are **not** performance predictions for actual 1080p/30fps recordings or Windows.
- FFmpeg and FFprobe were executed locally, not through GitHub Actions.

## Reproduction
From `video_analyzer`:

```sh
python -m unittest -v test_offline_four_table_visual_timeline.py
python offline_four_table_visual_timeline.py /path/to/recorded.mp4 /path/to/NEW_timeline.json --tables 4 --interval 1 --threshold 0.08
```

The test suite creates a 12-second synthetic fixture using FFmpeg; no poker recording is needed. The separate 60-minute benchmark uses a static 1-fps generated video with quadrant changes, not a real session.

## Not verified / blockers
- No authorized, annotated 3–5 minute real PLO5/PLO6 video was provided. Hand-boundary precision/recall, OCR, action recognition, player identification and actual hand reconstruction are **unmeasured**.
- Static quadrants are assumptions; manually selected/resized ROIs, overlapping windows, animated UI, scene cuts and real table movement are not yet handled.
- A one-hour 1-fps 320×192 synthetic video does not establish throughput, memory use, or accuracy for 4 simultaneous 1080p tables at normal frame rate. No Windows execution or end-to-end MP4 clip verification was performed in this cycle.
- No GitHub Actions used; no changes to main, production, credentials or expenses.

## Next
- Add optional manually configured ROIs and event review/annotation schema to associate each activity window with a tentative hand ID, preserving source PTS.
- Measure visual detection against authorized human-annotated real footage once supplied; integrate candidate windows into FFmpeg MP4 clip selection only after review.
