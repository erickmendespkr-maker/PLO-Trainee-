# Cycle 128 — offline FFmpeg batch extraction and end-of-video timing diagnostics

Scope: `docs/VIDEO_ANALYZER_SCOPE.md`; only prerecorded, authorized PLO5/PLO6 video. No live integration, playable tables, AI opponents, credentials or paid services.

## Added

- `offline_ffmpeg_batch_frame_provenance.py`: one FFmpeg **video decode pass** for up to 16 requested frame indices, then crops the extracted PNGs. Supports multiple crops from the same decoded frame, maintains input request order, captures FFmpeg `showinfo` PTS (including VFR), checks SHA-256 before and after, verifies PNG sizes and dimensions, and emits the existing Cycle-126 evidence-manifest format. Full-frame temporary PNGs are deleted on success; the new output directory is removed on failure. Still decodes the entire recording once: **not yet an optimized seek-based extractor for hour-long sessions**.
- `offline_ffmpeg_clip_end_audit.py`: compares video packet presentation spans from FFprobe between source and exported clip. Classifies differences larger than a one-frame tolerance as shorter/longer; does not modify frames or prove visual correspondence. Rejects packet timestamps without durations rather than estimating missing end time. Provides a JSON report for investigating last-frame clip discrepancies.

## Synthetic verification

Run from `video_analyzer/`:

```sh
python -m unittest discover -p 'test_offline_*.py'
python offline_ffmpeg_batch_frame_provenance.py ../demo/sample_source.mp4 ../demo/ledger.json ../demo/requests.json ../demo/new_batch_frames
python offline_ffmpeg_clip_end_audit.py ../demo/sample_source.mp4 ../demo/clip_to_end.mp4 1 ../demo/new_clip_report.json
```

- 19 new batch tests + 14 new clip audit tests passed locally.
- 222 selected tests across the available 11 `test_offline_*.py` modules passed locally. This is **not** the entire repository suite and not remote CI.
- Synthetic example: a 2-second video cut from second 1 to end produced a 1-second clip with a 0-second presentation-span difference. A deliberately shortened 0.5-second clip was classified `shorter_than_expected` with -0.5-second difference.
- No user video was available. No real OCR accuracy, PLO5/PLO6 hand reconstruction, 40–60-minute throughput, or EV correctness was established.

## Limitations / next cycle

- Source video still requires one full decode pass. Investigate bounded keyframe seeking with a PTS index for long recordings, and verify with VFR and codec B-frames.
- Packet timing audit cannot establish visual equality of source and clip final frame; a hash/perceptual comparison of decoded last frames is the next step.
- Both modules are diagnostic and preserve `equity_ev_authorized: false` for unverified visual evidence.
- FFprobe output is bounded after collection, not while the subprocess is running. Large or malformed inputs should be handled by a future streaming parser / resource-limited process.