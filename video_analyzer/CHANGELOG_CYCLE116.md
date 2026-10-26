# Cycle 116 — Offline MP4 video PTS normalization (synthetic evidence)

Scope: `docs/VIDEO_ANALYZER_SCOPE.md`; recorded PLO5/PLO6 only. No live poker, simulated playable tables, opponents, wagers, credentials or paid services.

## Changes

- `offline_manual_clip_export.py`: apply `setpts=PTS-STARTPTS` after optional crop so a manually selected cut starting between source frames has a zero-based *video stream* PTS origin. Preserve source VFR cadence with `-fps_mode:v passthrough`, rather than manufacturing constant-rate frames. Use FFprobe to validate output video stream `start_time` (within 25 ms of zero) and stream duration (within 250 ms of requested window), independently of subtitle/container duration. Refuse to publish if those checks fail. Record measured stream start/duration/shortfall and explicitly keep frame-exact, hand, and strategic verification flags false. Preserve the original sidecar status/schema version for compatibility.
- `offline_clip_visual_alignment.py`: guide three visual seek positions using observed decoded *clip* frame timestamps. This avoids requesting an undecodable end-of-stream timestamp on VFR cuts. The PTS of the *returned pixels* is not established and the visual report remains observational.
- `test_offline_clip_decoded_pts_comparison.py`: update the synthetic CFR expectation from the previously observed nonzero clip start (0.1 s) to the corrected zero-based video stream start.
- `test_offline_clip_visual_alignment.py`: assert PTS-guided sampling on CFR and VFR sources.
- `test_offline_clip_temporal_rebase.py`: 13 new tests covering non-frame-aligned cuts, VFR cadence, crop, audio/subtitle, four manual tables, output integrity, overwrite protection, nonzero-PTS and duration guards, and malformed metadata.

## Reproducible local checks

From `video_analyzer/`, with FFmpeg/FFprobe installed:

```bash
python -m unittest -v \
  test_offline_manual_clip_export \
  test_offline_clip_frame_pts_audit \
  test_offline_clip_visual_alignment \
  test_offline_clip_decoded_pts_comparison \
  test_offline_clip_review_page \
  test_offline_session_review_index \
  test_offline_clip_temporal_rebase
```

Local result on 2026-10-26: **125 selected tests passed** (112 existing + 13 new). This is **not** the complete repository test suite. See `selected_tests.log` in the cycle artifact.

## Synthetic demonstration

Source: 10 fps 160x120 artificial pattern, 4 seconds. Manually selected 0.55–2.55 s, without crop.

| Measurement | Before (Cycle 115) | After (Cycle 116) |
|---|---:|---:|
| Exported video stream start PTS | 0.100 s | 0.000 s |
| Exported video stream duration | 1.900 s | 1.900 s |
| Requested selection duration | 2.000 s | 2.000 s |
| Video stream shortfall | 0.100 s | 0.100 s |

The new report exposes the **remaining 0.100 s video duration shortfall**. The subtitle track/container can span 2.000 s, but this does **not** mean 2.000 s of decoded video frames are present. No filler frames are synthesized. The visual spot-check compared three positions; synthetic mean normalized grayscale MAE was 0.002469. That metric does not establish exact frame identity.

## Limitations / blocked

- Exact source-to-exported frame correspondence is **not** proven. Rebased stream PTS is not evidence of correct hand boundaries, OCR, equity or EV.
- Nonzero source recording PTS origins, highly sparse VFR, unusual codecs and hour-long recordings require further validation.
- The 100 ms video duration shortfall remains. Audio/video alignment was not independently measured, although an audio stream is preserved in synthetic tests.
- No authorized annotated real PLO5/PLO6 session was supplied. Real OCR accuracy and end-to-end analysis are **not verified**.
- No CI or full repository suite was run in this cycle.
