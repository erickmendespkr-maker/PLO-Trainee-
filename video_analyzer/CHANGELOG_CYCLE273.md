# Cycle 273 — direct relative-path FFmpeg fix and offline review queue prototype

## Published and verified

- Fixed the original `offline_reviewed_subtitled_batch_export.py` to resolve a relative recording path before FFmpeg changes its subprocess working directory for the subtitles filter. This fixes the original standalone exporter, not just the boundary-to-clips wrapper.
- Added a regression test that runs the standalone exporter from a different current directory using a relative video path.
- **30/30 local selected tests passed** (14 exporter tests, including the new relative-path case, and 16 offline review-queue prototype tests). The published exporter and test file Git blob SHAs matched the locally tested files.
- Tests used a short artificial video and the existing four-region synthetic fixture; no GitHub Actions, production, live poker integration, paid services, or secrets.

## Separate local prototype (not yet committed)

`offline_hand_ocr_review_queue.py` is available in the Cycle 273 downloadable test bundle. It associates unreviewed OCR candidates with manually annotated hand intervals per table, validates source and crop hashes, uses an explicit supplied source-PTS origin, records unmatched observations, and never promotes OCR to verified cards/actions or equity/EV. The local prototype passed 16 tests. It has **not** been integrated into the repository in this cycle and should not be described as deployed.

## Not verified / blockers

No authorized annotated real PLO5/PLO6 recording is available. OCR precision on poker tables, full original FFmpeg/Tesseract orchestration, long 40–60 minute sessions, PTS origin independent verification, Monte Carlo/EV integration, and end-to-end automatic hand reconstruction remain unverified. Synthetic tests do not establish real recognition accuracy.

## Next

Commit and integrate the local review queue after schema review; validate original FFmpeg/Tesseract chain without mocks, independently derive/verify the PTS origin, and keep a manual confirmation gate before equity/EV or automated clip selection.
