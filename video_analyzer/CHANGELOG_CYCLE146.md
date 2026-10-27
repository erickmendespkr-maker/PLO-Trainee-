# Cycle 146 — offline four-table samples and visual-change evidence

Scope: `docs/VIDEO_ANALYZER_SCOPE.md`. This is offline/asynchronous review of recorded, user-authorized MP4/WebM only. No playable tables, live assistance, inferred hidden cards, or integration with poker clients.

## Implemented

- Published the previously local `offline_four_table_sample_review.py` and its 26 synthetic tests, with exact Git blob SHA parity to the tested local files.
- `build` validates a human-declared 1–4 region grid/manual layout, extracts PNG frames and crops with FFmpeg, records **decoded source PTS** separately from requested seek time, and writes an offline HTML review panel plus SHA-256 manifest. Outputs are create-only and fail-closed; no OCR/hand facts are claimed.
- `verify_bundle` validates the sample manifest, image dimensions/hashes, optional source video hash, and all review flags.
- Added `offline_four_table_change_candidates.py` and 9 tests. It reads verified crops, reduces each to a 16×16 grayscale FFmpeg feature, and reports normalized mean absolute pixel differences between adjacent samples, separately per region. A thresholded **visual-change candidate** is not a verified hand boundary or poker action. Reports are create-only JSON.
- Synthetic 3-second, four-quadrant video: top-left quadrant changes at 1 second. Three source timestamps, 4 regions, 8 consecutive comparisons; only the first top-left comparison was flagged. Example difference 0.70539216 versus 0.12 threshold. The remaining seven comparisons were not flagged.

## Verified locally

`python -m unittest -v test_offline_four_table_change_candidates.py test_offline_four_table_sample_review.py test_offline_four_table_layout_contract.py test_table_regions.py test_video_segments.py`

**58 selected tests passed** on the working container with FFmpeg/FFprobe; no GitHub Actions were invoked. Source and test files' published Git blob SHAs were compared with local `git hash-object` results. No changes to `main`.

## Not verified / limitations

- No annotated real PLO5/PLO6 session video was available. OCR accuracy, cards/actions, hand segmentation, equity/EV correctness on reconstructed real hands, and 40–60 minute four-table throughput are **not** validated here.
- A change in pixel appearance is not a hand boundary. Sparse samples can miss hands entirely; compression, animations, and layout changes can create false positives. Human review is required.
- Full repository test suite and remote CI were not run.

## Next

Add confidence-aware OCR field proposals (with provenance and manual review) using only recorded frames, then test against an annotated authorized 3–5 minute sample when available. Benchmark longer synthetic recordings without extrapolating to real-world accuracy.
