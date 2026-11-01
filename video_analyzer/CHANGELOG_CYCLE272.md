# Cycle 272 — reviewed hand boundaries to subtitled MP4 clips

## Scope
Offline/async video review only, consistent with `docs/VIDEO_ANALYZER_SCOPE.md`. New `offline_reviewed_boundary_clip_pipeline.py` connects human-annotated hand intervals to the existing `offline_reviewed_subtitled_batch_export.py`. It does not detect hands, recognize cards, choose decisions, or calculate equity/EV. Manual annotations, review flags and explanations are **self-attested**, not authenticated.

## Inputs and command

```bash
python video_analyzer/offline_reviewed_boundary_clip_pipeline.py recording.mp4 hands.json selections.json NEW_OUTPUT_DIRECTORY
```

`hands.json` uses the existing boundary-label schema:

```json
{"schema_version":1,"status":"human_annotated_hand_boundaries","recording_sha256":"<actual 64-character lowercase SHA-256>","hands":[{"table_id":1,"start_seconds":0.2,"end_seconds":1.2}]}
```

`selections.json`:

```json
{"schema_version":1,"time_basis":"playback_seconds","recording_sha256":"<same SHA-256>","selections":[{"review_id":"r1","hand_index":0,"table_id":1,"explanation":"Manually reviewed interval","human_reviewed":true,"crop":{"x":0,"y":0,"width":320,"height":180}}]}
```

`hand_index` is **zero-based** in the supplied `hands` array. Times are relative to playback start, **not source PTS**. Both JSONs must refer to the actual video bytes. Table crops are even-pixel rectangles inside the video frame. Output directory must not exist. At most 12 reviewed clips are exported, each at most 180 seconds, with subtitle burn-in, SRT, hashes and JSON provenance. The result contains `review_manifest.json`, `clips/` and `pipeline_report.json`.

## Verified locally — 2026-11-01
- **44/44** selected tests passed: 31 new bridge tests plus 13 existing exporter regression tests, run with Python 3.13, FFmpeg and FFprobe; no GitHub Actions.
- Generated **four** synthetic MP4s from one two-second 640x360 10-FPS recording. FFprobe measured **1.000 s** for each cropped/subtitled clip.
- Tested mismatched video SHA, wrong table, duplicate hand index, same-table overlap, unreviewed selection, unsafe subtitle/crop, duplicate JSON keys, NaN, symlink inputs, output collision and failed FFmpeg. Failed operations did not publish the requested output.
- Discovered a relative-path failure in the original exporter invocation because subtitle rendering changes working directory. The bridge now resolves the recording path before calling the exporter, with a CLI regression test.
- Confirmed published Git blob SHA values against the exact local files tested.

## Not verified / blockers
- The four-region video is artificial, with **manually supplied intervals**; this does not measure poker OCR, hand recognition, mathematical correctness or clip selection accuracy.
- End-to-end real PLO5/PLO6 reconstruction, 40–60 minute performance, Windows, 4K, nonzero source PTS, full original FFmpeg/Tesseract pipeline, and equity/EV integration remain unverified.
- Requires an authorized and human-annotated 3–5 minute poker recording for a real recognition benchmark.
- The underlying exporter checks a new output path before rename, but cross-process races are not completely eliminated. Human-review status is a supplied flag, not authentication.

## Next
Integrate a manual review UI with hand boundary evidence, then validate the original sampler/Tesseract chain without test doubles. Only reviewed complete hand data should reach a future Monte Carlo equity/EV stage, with explicit assumptions and confidence.
