# Cycle 258 — bounded synthetic FFmpeg four-table duration and ROI probe

## Scope and guardrails
Consulted `docs/VIDEO_ANALYZER_SCOPE.md`. Added only an offline, synthetic performance/evidence probe. No live poker, table gameplay, betting integration, credentials, paid services, production, or `main` changes.

## New components
- `offline_ffmpeg_four_table_scale_probe.py`: generates a disposable MPEG-4 fixture with four known, solid-color quadrants; uses FFmpeg seeks, `showinfo` decoded PTS and 160x120 PNG ROI crops; validates each table's pixel identity and records SHA-256, sizes, timings, and Linux child-process RSS high-water. All fixture/crop files are removed after each run. Output JSON must not exist beforehand.
- `test_offline_ffmpeg_four_table_scale_probe.py`: 8 unit/integration tests, including actual FFmpeg extraction for 4 tables × 4 timestamps, crop pixel verification, invalid duration/sampling, symlink protection and no overwrite.

## Locally verified, exact published code
- 8/8 tests passed using FFmpeg 7.1.5 on Linux. Local source and test Git blob SHA-1 match their respective GitHub branch blobs.
- 40-minute synthetic fixture (2,400 seconds at **1 frame/second**, 320x240): 20 verified ROI crops, 2.588730 seconds total wall time, 1.287848 seconds crop extraction, 2,002,508 bytes fixture, 98,188 KiB maximum child-process RSS high-water.
- 60-minute synthetic fixture (3,600 seconds at **1 frame/second**, 320x240): 28 verified ROI crops, 3.776693 seconds total wall time, 1.897797 seconds crop extraction, 3,003,324 bytes fixture, 99,332 KiB maximum child-process RSS high-water.
- Both synthetic fixtures were generated and removed locally; results are preserved as JSON with frame PTS and image hashes.

## Reproduce (offline)
```bash
cd video_analyzer
python -m unittest -v test_offline_ffmpeg_four_table_scale_probe
python offline_ffmpeg_four_table_scale_probe.py new_40min.json --seconds 2400 --interval 600
python offline_ffmpeg_four_table_scale_probe.py new_60min.json --seconds 3600 --interval 600
```

## Important limitations
- **This does not benchmark real 40–60-minute poker recordings.** Source is 320x240, 1 fps, four solid-color quadrants, not four visually complex poker tables. Each sample is a manually known quadrant. The numbers are **not** estimates for full OCR, hand reconstruction, actual 1080p/4K uploads, or Windows.
- PTS tolerance is one synthetic 1-fps frame; variable-frame-rate and non-zero start-time sources remain unverified.
- RSS is the Linux maximum child-process high-water mark, not total or concurrent memory consumption.
- No OCR, card/hand recognition, Monte Carlo or EV was run in this cycle; no decision recommendation is produced.
- Existing `offline_video_ingest_probe.py` and the review-to-math chain were not exercised together in this cycle. The new probe is an independent synthetic FFmpeg scale check.

## Blocker and next cycle
An authorized, annotated 3–5 minute PLO5/PLO6 video is still required for measuring visual recognition accuracy. Next: connect the synthetic four-table ROI fixture to the existing offline ingest/provenance pipeline and test VFR/PTS behavior; then add a guarded OCR accuracy comparison against human annotations when a real sample is available.
