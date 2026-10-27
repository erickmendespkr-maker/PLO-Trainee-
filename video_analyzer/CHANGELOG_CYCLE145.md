# Cycle 145 — four-table layout contract and synthetic visual probe (2026-10-27)

## Published to `feature/plo5-plo6-training`
- `offline_four_table_layout_contract.py`: strict deterministic contract for 1–4 grid/manual table regions, source dimensions, session duration, 1–8 ordered sampling times, canonical SHA-256 of layout, and fail-closed review flags. It does **not** detect tables, OCR cards, reconstruct hands, or authorize equity/EV/clips.
- `test_offline_four_table_layout_contract.py`: 14 synthetic tests for odd dimensions, manual regions, overlap, booleans, NaN, timestamps, and scope limits.
- No changes to `main`, production, secrets, live poker integration, or GitHub Actions.

## Local-only FFmpeg proof of concept (not yet committed)
- `offline_four_table_sample_review.py` and its 26 synthetic tests are in the cycle's downloadable local bundle, **not** in the GitHub branch. It produces source-PTS-bound PNGs, four region crops per sample, SHA-256 manifests, and offline HTML review; verification rejects altered files.
- Local selected suite: 49 passed, 0 skipped = 14 contract tests + 26 FFmpeg POC tests + 9 existing regression tests. Existing dependency files were byte-matched against GitHub blob SHAs.
- A 60-second 640×360, 5 fps H.264 synthetic recording with four colored quadrants produced 4 full-frame PNGs, 16 crops, and a verified JSON report. Local wall time 2.37 s; peak RSS 97,184 KB. These are not results for a real 40–60-minute session.
- Additional POC tests covered H.264/MP4, VP9/WebM and VFR timestamps; no OCR or card/action recognition.

## Blockers / next
No authorized annotated 3–5-minute PLO5/PLO6 sample is available. OCR accuracy, hand reconstruction and hour-long four-table throughput are unverified. Next cycle: integrate/publish the local FFmpeg sample-review POC, connect its reviewed regions to the existing OCR queue, and benchmark against authorized annotated footage when provided.
