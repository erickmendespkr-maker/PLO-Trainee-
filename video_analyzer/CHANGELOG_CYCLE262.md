# Cycle 262 — batched source-frame ROI verification

Scope: **offline/asynchronous** analysis of recorded PLO5/PLO6 sessions only. No playable tables, real-time assistance, account integration, or wagering.

## Implemented

- Added `offline_ingest_roi_batch_pixel_audit.py`: performs the original independent full PTS/SHA/JPEG audit, then compares selected crops against source frames decoded in **one FFmpeg `select` pass**, grouped by exact frame index. Maintains the existing 64-crop bound and 12 RGB mean-error tolerance.
- The batch decoder uses a private temporary PNG directory, checks exact frame count and source geometry, caps individual/aggregate PNG sizes, and cleans up on failure. Source files are not modified.
- Updated `offline_ingest_audited_pipeline.py` to use the batched pixel auditor. The output chain report records decoder strategy and FFmpeg decode pass count, while retaining full PTS/SHA coverage and explicit partial pixel-check coverage.
- Fixed `choose_spotcheck` to redistribute unused pixel-check budget when some tables have fewer samples, while preserving deterministic temporal coverage.
- Added `test_offline_ingest_roi_batch_pixel_audit.py` with adversarial cases and integration against the original ingest/auditors; added one budget-redistribution regression test. Added a reproducible synthetic 720p benchmark script.

## Verified locally

- The four pre-existing source modules matched the exact GitHub blob hashes before modification.
- **52/52 selected tests passed** using Python 3.13 and FFmpeg 7.1.5 (14 new/extended + 38 previous). Tests include VFR, four tables, source/crop tampering, output rollback, frame selection, geometry, and legacy-vs-batch identical ROI results.
- In one synthetic **60-second 1280×720, 10 FPS** four-table benchmark with 52 crops and 13 distinct source frames, legacy pixel verification took **4.215 s**, batch verification **1.807 s** (observed **2.33×** speedup). Results matched exactly. Timings exclude ingestion and are not representative of 40–60 minute production sessions.
- All five new/updated Python files were checked against GitHub blob SHA after publication.

## Not verified / blocked

- No authorized, human-annotated 3–5 minute PLO5/PLO6 recording supplied; real OCR, cards, actions and hand-boundary accuracy remain unmeasured.
- No Windows test, 4K/Full HD hour-long throughput, peak-memory profiling or full repository test suite.
- The decoder still scans source frames up to the latest selected frame, and stores up to 64 temporary PNGs. Aggregate size is checked after FFmpeg exits, so this is a bounded validation stage rather than a hard disk-quota sandbox.
- Neither the pixel audit nor this optimization authorizes equity/EV from unreviewed visual evidence.

## Next

- Add incremental source-frame decoding or seek-indexed batches for hour-long recordings, with measured peak disk/RAM and bounded concurrency.
- Add synthetic visual hand-boundary fixtures and confidence-labeled, human-reviewable observations; only feed reviewed evidence into the already tested mathematical path.
