# Cycle 263 — offline OCR evaluation v2 (synthetic only)

Scope: asynchronous evaluation of recorded PLO5/PLO6 OCR proposals against manually labeled observations. No live play, poker integration, wagering, hidden-card inference, equity or EV from unreviewed data.

## Implemented

- New `offline_recognition_benchmark_v2.py`, complementary to existing `recognition_metrics.py` without changing its legacy interface.
- Deterministic chronological one-to-one matching within `(table_id, field)`, maximizing timestamp-match count in O((N+M) log(N+M)) sorting time, rather than repeated global scans. Matched timestamp errors are recorded; this does not minimize total timestamp error.
- Distinguishes OCR coverage, accuracy conditional on answered labels, strict precision/recall/F1 (wrong predictions count as both FP and FN), and unmatched answered/abstaining predictions.
- Reports per-table/per-field metrics and Wilson 95% binomial intervals with explicit caveats about label authenticity, calibration and generalization.
- Enforces bounds, strict numeric/card value types, unique labeled keys, finite timestamps, duplicate JSON key rejection, SHA-256 provenance, create-only atomic report publication, and read-only input behavior.

## Verified locally

- 23/23 new tests passed under Python 3.13.5, including one-to-one temporal matching, multiple tables/fields, abstention, wrong labels, false positives, duplicate labels/JSON keys, invalid booleans, NaN, symlink rejection, no-overwrite publication, and 4,000 synthetic observations.
- Synthetic four-table demonstration JSON produced and checked; **not a measure of real OCR performance**.

## Not verified / blocked

- No authorized human-labeled real PLO5/PLO6 video. No real-video OCR precision, recall, hand-boundary accuracy or Tesseract confidence calibration can be claimed.
- This standalone evaluator has not yet been connected to the OCR review UI or the original end-to-end ingestion chain. Windows and full repository tests remain unverified.

## Next

- Connect benchmark report to the existing offline OCR review/export flow while preserving provenance and human correction gates.
- Validate recognition and temporal hand boundaries against authorized annotated real-video data when available.
