# Cycle 267 — recording-bound OCR benchmark with real FFmpeg/Tesseract synthetic evidence

## Scope
Consulted `docs/VIDEO_ANALYZER_SCOPE.md`. Offline, post-session, no playable tables, no live platform integration, no betting decisions. A new **diagnostic** wrapper checks that an OCR evaluation actually refers to the same local recording and exact crop files as its source region manifest.

## New module
- `offline_verified_ocr_benchmark.py`: validates actual MP4/WebM SHA-256 bytes and FFprobe metadata, source manifest provenance and fail-closed flags, frame and crop PNG SHA-256/dimensions, non-overlapping table regions, candidate table/sample/crop SHA/path/PTS/ROI and human-label timestamp alignment.
- Invokes the existing `offline_four_table_ocr_benchmark_bridge.build` and preserves its strict abstention behavior, Wilson intervals, and unreviewed status.
- Uses create-only report publication; refuses overwritten outputs, symlink input files, unsafe paths, changed source files, and promoted OCR.
- Does **not** infer cards, actions, hand boundaries, ranges, equity, EV, or clips.

## Local verification
- 37/37 tests passed: 21 new wrapper tests plus 16 existing OCR bridge tests.
- Generated an actual two-second, 640×360 MP4 with four synthetic quadrants; extracted a source PNG and four crop PNGs with FFmpeg; invoked actual Tesseract 5.5.0 with `--psm 6 tsv` on four bounded ROIs. Raw OCR outputs were `12`, `23`, `34`, `45`. The original OCR benchmark bridge reported 4/4 agreement against synthetic labels. This is **not** a measurement of poker-video OCR accuracy.
- The local test exercised the original Tesseract TSV parser logic from the repository through a local parser-only copy. The **full** original `offline_four_table_ocr_proposals.scan` and `offline_four_table_sample_review.build` functions were **not** executed together; their output schemas were constructed synthetically. The next cycle must run the complete original chain.
- FFmpeg/FFprobe 7.1.5, Python 3.13.5, Tesseract 5.5.0; local Linux only. No GitHub Actions.

## Limitations
- A verified hash proves byte consistency, not that the crop corresponds to the correct original video pixels; the separate ROI pixel auditor remains necessary.
- Synthetic overlay text is much simpler than real PLO5/PLO6 HUDs. Human labels are not authenticated, OCR confidence is not calibrated, and 4/4 is not a real-world accuracy claim.
- No authorized, human-annotated 3–5-minute recording was available. Windows and complete 40–60-minute end-to-end video analysis remain unverified.

## Next
- Execute the full original `offline_four_table_sample_review.build` -> `offline_four_table_ocr_proposals.scan` -> `offline_verified_ocr_benchmark.run` sequence with FFmpeg/Tesseract on a generated synthetic recording.
- Bind the existing pixel auditor to this provenance wrapper, then link human-reviewed observations to candidate hand intervals. Do not authorize equity/EV from raw OCR.
