# Cycle 115 — Decoded source/clip PTS proximity audit (2026-10-26)

**Repository/branch:** `erickmendespkr-maker/PLO-Trainee-` / `feature/plo5-plo6-training` only. **Scope:** offline analysis of prerecorded PLO5/PLO6 sessions under `docs/VIDEO_ANALYZER_SCOPE.md`; no live poker, AI opponents, playable tables, production, credentials or spending.

## Added

- `offline_clip_decoded_pts_comparison.py` uses FFprobe `-show_frames` / `best_effort_timestamp_time` on both an authorized local source video and a manually exported MP4, observing decoded-frame timestamps for both. Sampling is bounded by 210 seconds, 50,000 frame rows and a 2 MB FFprobe response; up to 11 exported-frame timestamps are compared to nearby observed source timestamps.
- The *nominal* source position for each sampled clip PTS is `manual_selection_start + (decoded_clip_pts - clip_video_stream_start_pts)`. Nearest observed source PTS, signed/absolute offsets, a configurable proximity tolerance, frame-spacing statistics and local CFR/VFR spacing observations are reported.
- A nonzero clip stream start PTS is **recorded rather than hidden**. The source stream still requires a near-zero origin; explicit normalization of nonzero-origin recordings remains future work.
- The report checks the source and exported clip SHA-256 against the original Cycle 109 sidecar, verifies manual table/crop and duration consistency, rejects falsely verified/automatic-selection claims, symlinks, overlapping paths, malformed/duplicate-key JSON and output overwrites. Input digests are rechecked before exclusive report creation.
- Output flags explicitly state `actual_decoded_frame_pts_measured: true`, but `frame_exact_export_verified: false`, `hand_start_or_end_pts_verified: false`, `hand_reconstruction_verified: false`, `strategic_error_established: false` and `automatic_clip_selection_authorized: false`.

## Synthetic observation: exporter timing gap

In the FFmpeg 7.1.5 synthetic fixture, a **2.0 s** human-selected interval (`0.55–2.55 s`) exported by the existing `offline_manual_clip_export.py` resulted in an MP4 video stream with **start PTS 0.100 s** and **video stream duration 1.900 s**. The new audit records a **0.100 s video-stream shortfall** and samples 11 decoded-frame PTS positions; maximum observed nearest-source PTS proximity was **0.050 s**. This is an observation for one artificial fixture, not a general guarantee or evidence of exact frame correspondence. The original exporter was not changed this cycle.

## CLI

```bash
python video_analyzer/offline_clip_decoded_pts_comparison.py \
  recorded_source.mp4 exported_clip.mp4 exported_clip.json new_pts_report.json \
  --tolerance 0.125
```

The sidecar JSON must be the original manual-export sidecar. The report is a **new** JSON file and will not overwrite an existing path. No network, live input or poker service is accessed.

## Verified locally, synthetic only

- `python -m unittest -v test_offline_clip_decoded_pts_comparison`: **22 passed**.
- `python -m unittest -v test_offline_clip_decoded_pts_comparison test_offline_manual_clip_export test_offline_clip_frame_pts_audit test_offline_clip_visual_alignment test_offline_clip_review_page test_offline_session_review_index`: **112 passed** (selected regression tests, not full exact-branch suite).
- Tests cover real FFmpeg CFR/VFR media, nonzero clip origin, four manual table IDs, source PTS origin rejection, SHA tampering, duplicate JSON keys, invalid verification flags, geometry/duration mismatch, symlinks, output collisions, invalid/oversized PTS responses, source mutation and report provenance.
- After GitHub publication, both new source/test Git blob SHAs matched the locally tested files.

## Not verified / blocked

- No authorized, annotated real PLO5/PLO6 video; cannot measure OCR, hand boundary detection, action accuracy, equity/EV validity or complete 40–60 minute throughput.
- Source sampling uses FFprobe keyframe-seeking intervals and may omit frames; PTS proximity **does not** establish decoded-frame pixel identity or a correct trim. Existing exporter timing discrepancy requires investigation and a tested fix.
- No full repository test suite or remote GitHub CI was run. Windows browser UI remains unverified.

## Next cycle

1. Investigate the existing manual exporter's nonzero clip PTS origin and short video stream duration; develop a backward-compatible, synthetic-tested trim normalization fix without asserting hand boundaries.
2. Add manual review state/provenance for low-confidence OCR and hand intervals, without promoting hypotheses to facts.
3. Validate against a short authorized annotated PLO5/PLO6 recording when supplied.
