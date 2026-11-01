# Cycle 268 — independent source-video pixel replay for four-table PNG evidence

## Scope and rationale
Read `docs/VIDEO_ANALYZER_SCOPE.md`. This remains offline/async analysis of recorded PLO5/PLO6 sessions only. The cycle addresses an evidence-integrity gap in the Cycle 267 OCR benchmark: a source manifest can have correct hashes for modified PNGs without proving that the PNG pixels came from the recording. This audit does not infer poker hands or authorize equity/EV.

## New files
- `offline_region_sample_pixel_audit.py`: validates source recording bytes and FFprobe metadata using Cycle 267's existing validation, checks all source frame/crop hashes and geometry, independently enumerates FFprobe frame PTS, matches sample PTS to decoded frame indices, replays all selected frames with one FFmpeg `select` pass, and compares exact RGB pixels for full frames and table crops. Emits a create-only JSON report with explicit false math/clip-authorization flags.
- `test_offline_region_sample_pixel_audit.py`: 12 synthetic tests including 1-frame/4-table and 2-frame/8-crop replay, updated-hash crop swaps, updated-hash source-frame replacement, PTS mismatch, changed video bytes, promotion flags, missing FFmpeg, symlink output and create-only behavior.

## Verification
- Local Linux, Python 3.13.5, FFmpeg/FFprobe 7.1.5, Pillow: **28/28 tests passed** (12 new and 16 previous OCR bridge regressions). Test log included in local archive.
- Executed the new auditor on the existing Cycle 267 synthetic MP4 and four-crop bundle: 1 source frame and 4 crops passed. The bundle is synthetic, not a real poker recording.
- Published module and tests on `feature/plo5-plo6-training` only; the Git blob SHA of each published file was compared with its tested local counterpart.

## Limitations
- This audit validates pixel provenance of sparse manually specified table regions, not correct region selection or OCR semantics. Exact RGB equality is deliberately strict; videos with different decoder color transforms or altered frame processing will fail closed.
- It is bounded to 8 frames, 32 crops and 160 MiB of decoded PNGs, with a 300-second FFmpeg timeout; a one-hour 4K throughput benchmark has **not** been run.
- No authorized annotated 3–5 minute PLO5/PLO6 recording; no real OCR accuracy or complete reconstruction/EV/clip pipeline was validated.
- The original `offline_four_table_sample_review.build` and `offline_four_table_ocr_proposals.scan` were not executed together in this cycle. The full original chain remains pending.

## Next
Run the original four-table sample-review builder and OCR scanner together with the new pixel auditor and Cycle 267 benchmark on an annotated synthetic MP4, then compare against human labels. Test VFR/nonzero-PTS video and document any mismatches. Preserve manual review before math and clip selection.
