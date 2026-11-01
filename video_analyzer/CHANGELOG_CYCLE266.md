# Cycle 266 — verify original video bytes before evaluating hand boundaries

## Scope

Consulted `docs/VIDEO_ANALYZER_SCOPE.md`. Adds a **recording-provenance check** to the existing offline, non-authoritative hand-boundary evaluator. This does not detect hands or infer poker facts, and does not authorize equity/EV.

## Implemented

- `offline_verified_video_boundary_benchmark.py` wraps the existing `offline_hand_boundary_benchmark.evaluate` after hashing the actual local MP4/WebM bytes, comparing them to **both** input manifests, and validating one video stream and bounded duration using FFprobe.
- Supports explicit `--timeline-basis video-relative` or `--timeline-basis source-pts` to prevent confusion when the original video starts at a nonzero PTS. Rejects proposal/label intervals beyond the declared video duration.
- Rejects symlink inputs, invalid file sizes, unsupported extensions, duplicate JSON keys (via the original evaluator), overwritten outputs, missing FFprobe, fake MP4 content, mismatched hashes, and promoted unreviewed proposals.
- Rehashes the video and both manifests before publishing a create-only JSON report via a hard link. No external URLs or live-poker integration.
- Keeps `human_labels_verified_against_video`, `visual_hand_boundary_accuracy_verified`, `hands_reconstructed`, and `ready_for_equity_or_ev` all **false**. Hash verification does not establish that the human labels are correct.

## Verified locally

- **48/48 tests passed**: 17 new wrapper tests plus 31 existing boundary evaluator tests. Python 3.13.5; FFmpeg/FFprobe 7.1.5.
- The tests generated a real 3-second synthetic MP4 and an additional MP4 whose video stream starts at PTS 5.0 seconds; FFprobe, SHA-256, four-table interval agreement and rejection cases were exercised.
- The exact locally tested source files match the published Git blob hashes. The existing evaluator used was the exact file from the Cycle 265 package (`dd07add324510da92a643db6286a77490808f213`).
- No GitHub Actions, main changes, production changes, credentials, paid services, or live integrations.

## CLI

```bash
python video_analyzer/offline_verified_video_boundary_benchmark.py recording.mp4 proposals.json human_labels.json new_report.json --timeline-basis video-relative
```

For a source whose video stream PTS begins at 5.0 seconds, use `--timeline-basis source-pts` and annotate absolute source PTS. For timestamps starting at zero, use `video-relative`.

## Limitations and blockers

- The FFprobe metadata and SHA check are **not** frame-by-frame evidence of hand starts or ends. The test video is synthetic; no real PLO5/PLO6 footage was available.
- A real authorized, annotated 3–5-minute recording is still required to measure actual recognition and hand-boundary accuracy. Full 40–60-minute four-table performance, Windows behavior, OCR recognition, and complete MP4 export remain unverified.
- The original FFmpeg/Tesseract OCR scanner has not yet been exercised together with the Cycle 264 OCR benchmark bridge in this cycle.

## Next

- Exercise the original `offline_four_table_sample_review` + `offline_four_table_ocr_proposals` + `offline_four_table_ocr_benchmark_bridge` using FFmpeg/Tesseract on a synthetic four-table recording.
- Bind OCR and hand-boundary evidence to the same verified recording SHA and timestamp basis; keep all raw OCR observations unreviewed.
- Measure real-video precision and calibrate confidence once annotated authorized footage is available.
