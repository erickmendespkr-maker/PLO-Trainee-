# Cycle 117 — FFmpeg end-trim rounding guard and A/V timeline observation

Scope: `docs/VIDEO_ANALYZER_SCOPE.md`. Offline recorded PLO5/PLO6 review only. No playable tables, AI opponents, live capture, wagering, credentials, or paid services.

## Implementation

- `offline_manual_clip_export.py`: add a **1 ms output `-t` guard** to reduce FFmpeg's observed final-packet DISCARD behavior on synthetic 10 fps and 30 fps videos. This does not synthesize frames, does not guarantee exact source-frame boundaries, and can admit a frame within 1 ms of the requested end. Existing SHA-256, crop, no-overwrite, PTS rebasing, and duration checks remain in place.
- Probe the **optional audio stream** after export; record start/end offsets relative to video stream metadata. Missing audio is explicit. These are stream metadata comparisons, **not verified content synchronization**. Malformed or ambiguous audio timing fails closed.
- `test_offline_clip_decoded_pts_comparison.py`: replace an obsolete assertion that a positive video shortfall must exist with bounded shortfall checks.
- `test_offline_clip_duration_av_guard.py`: 12 new synthetic tests for CFR (10/30 fps), VFR, optional audio, EOF behavior, crop, no-overwrite, malformed audio metadata, and verification flags.

## Reproducible tests

From `video_analyzer/` with FFmpeg and FFprobe installed:

```bash
python -m unittest -v \
  test_offline_manual_clip_export \
  test_offline_clip_frame_pts_audit \
  test_offline_clip_visual_alignment \
  test_offline_clip_decoded_pts_comparison \
  test_offline_clip_review_page \
  test_offline_session_review_index \
  test_offline_clip_temporal_rebase \
  test_offline_clip_duration_av_guard
```

Local result on 2026-10-26: **137 selected tests passed** (125 previous selected + 12 new). This is not the full repository suite, and remote CI was not run.

## Synthetic measurements

| Test | Before (Cycle 116) | After (Cycle 117) |
|---|---:|---:|
| 10 fps source, manual selection 0.55–2.55 s: decoded clip frames | 19 | **20** |
| 10 fps source, same selection: video stream duration | 1.900 s | **2.000 s** |
| Same selection: video stream start PTS | 0.000 s | **0.000 s** |
| 30 fps source, same selection: decoded clip frames | Not measured | **60** |
| 10 fps source, selection ending exactly at source EOF | Not measured | **19 frames, 1.900 s** |

The EOF shortfall remains visible: the guard does not create an extra frame. Synthetic audio clip stream start offset was approximately 0 s, and end offset approximately 0.001 s. This does **not** prove waveform synchronization.

## Important limitations

- These are FFmpeg/FFprobe observations on synthetic inputs, not hand boundaries or source-to-export frame identity verification.
- A 1 ms trim guard is an implementation workaround with codec/container-specific behavior; it can include a boundary-adjacent frame and is not guaranteed for sparse VFR or unusual encoders.
- A selection ending at source EOF can still exhibit a video stream duration shortfall; report it instead of claiming an exact cut.
- Audio/video stream start/end metadata does not prove audio content is synchronized with video content.
- No authorized annotated real PLO5/PLO6 video was supplied. Real OCR, action recognition, mathematical correctness on real hands, and 40–60 minute end-to-end processing remain unverified.
- No main branch, production, secrets or expenses were modified.
