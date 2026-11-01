# Cycle 265 — offline hand-boundary agreement benchmark

## Scope

Read `docs/VIDEO_ANALYZER_SCOPE.md`. This cycle adds an independent evaluation tool for *proposed* start/end times of hands in previously recorded PLO5/PLO6 sessions. It is **not** a hand detector, poker simulator, live connector, or decision engine. It cannot authorize equity/EV or clips.

## Added

- `offline_hand_boundary_benchmark.py`: create-only CLI comparing proposed intervals with separately annotated human intervals for up to four tables, each recording bounded to four hours and each input bounded to 512 intervals.
- Requires an explicit matching claimed recording SHA-256 in both inputs, but **does not** check that claim against video bytes. Requires candidate status `needs_manual_review` and `ready_for_equity_or_ev: false`.
- Strictly validates intervals, table identity, disjoint intervals per table, confidence metadata as **uncalibrated**, source sample indices, JSON keys, finite numbers, file sizes, symlinks, output collisions and changing input files.
- One-to-one chronological dynamic programming matching maximizes matched intervals, then minimizes combined start/end timestamp error for ties. A match requires **both** endpoints to be within the configured tolerance; no prediction may be reused.
- Reports per-table and aggregate precision, recall, F1, false positives, misses, Wilson 95% sampling intervals, exact matched source indices and endpoint errors. Never claims real-video accuracy, calibrated confidence or reconstructed hands.

## Locally verified

- **31/31 unit/property tests passed**, Python 3.13. Tests include 1,000 randomized comparisons against exhaustive noncrossing matching and 1,000 randomized comparisons against unrestricted maximum-cardinality matching (small, nonoverlapping sequences).
- Synthetic 60-minute timeline across four tables: 320 human intervals and 315 synthetic proposals, 315 matches, 5 misses, 0 unmatched proposals; 100% precision and 98.4375% recall **only against constructed labels**.
- Measured one local CLI run of the 60-minute synthetic timeline at approximately **1.22 seconds** and **97,040 KB peak RSS** (system `/usr/bin/time`). This measures JSON evaluation, **not video processing**.
- No GitHub Actions, production, paid services, credentials, main-branch edits, or live poker integrations used.

## CLI

```bash
python video_analyzer/offline_hand_boundary_benchmark.py proposals.json labels.json new_report.json --tolerance-seconds 0.5
```

Candidate input:

```json
{"schema_version":1,"status":"unverified_offline_hand_boundary_proposals","ready_for_equity_or_ev":false,"recording_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","boundaries":[{"table_id":1,"start_seconds":10,"end_seconds":25,"status":"needs_manual_review","confidence_uncalibrated":0.6,"source_sample_indices":[1,2]}]}
```

Separate human-label input:

```json
{"schema_version":1,"status":"human_annotated_hand_boundaries","recording_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","hands":[{"table_id":1,"start_seconds":10.1,"end_seconds":24.9}]}
```

The tool requires *nonoverlapping* proposed and annotated hand intervals within each table. Overlapping proposals must be resolved upstream; this prevents double-counting and supports order-preserving matching.

## Not verified / blocked

- No authorized 3–5 minute human-labeled poker recording. No real-video hand-boundary accuracy, OCR correctness, end-to-end clips or Windows performance verified.
- No actual FFmpeg/Tesseract scanner invocation this cycle; the original scanner-to-OCR-benchmark integration remains a separate test target.
- Recording hashes are **input claims**. Annotations are not authenticated against original pixels.
- The 60-minute synthetic timeline contains JSON timestamps only, not 60 minutes of decoded video.

## Next

- Connect verified video sample evidence and conservative candidate hand-boundary extraction to this benchmark, without promoting unreviewed observations to poker facts.
- Run the original Tesseract scanner plus Cycle 264 OCR benchmark bridge on a generated synthetic video; compare outputs with independently prepared labels.
- Calibrate actual boundary and OCR precision on a short authorized annotated real recording when available.
