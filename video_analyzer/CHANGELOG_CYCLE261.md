# Cycle 261 — original offline ingest + independent provenance audits

Scope: recorded PLO5/PLO6 video only. No live integration, playable tables, betting or AI opponents.

## Implemented

- Added `offline_ingest_audited_pipeline.py`: invokes **the original** `offline_video_ingest_probe.build`, then `offline_ingest_pts_audit.audit` on **all** generated crops, then `offline_ingest_roi_pixel_audit.verify` on a bounded, deterministic, time-stratified sample from every table.
- Runs in a private staging directory; only publishes the completed output folder after both audits pass. A failed audit leaves no published result.
- Outputs `ingest/manifest.json`, `pts_audit.json`, `pixel_spotcheck.json`, and `chain_report.json`, including SHA-256 evidence, counts, selection and explicit coverage fraction.
- Preflights the maximum 512 PTS samples and 64 pixel spot checks; refuses unsupported budgets rather than silently skipping verification.
- Never authorizes OCR, hand reconstruction, equity or EV based on sampled pixels.

## Verification

- The local original ingest file matched the GitHub blob SHA `03e02872085627032d927b3c8380e91fbb425a50`.
- PTS auditor matched `bed726eb2ed622a50c6bd31e09f3fbd1f9907c0e`; pixel auditor matched `57b0f05ea8d5d26036f124a3492ca2cb14f6bfad`.
- 38/38 selected local tests passed (14 new + 24 existing), using FFmpeg/FFprobe, including real original ingest, four table quadrants, VFR, nonzero source PTS, a 65-second recording, partial vs full pixel checks, no-overwrite and rollback.
- A 2-second synthetic VFR recording yielded 12 ingested crops, all 12 PTS/hash audited, with 8 or 12 pixel checks depending on budget.
- The 65-second synthetic four-table case exercised full PTS auditing and partial pixel coverage; this does **not** validate 40–60 minute throughput.

## Not verified / blockers

- No authorized annotated real recording supplied; OCR accuracy, table/hand reconstruction and human review precision cannot be measured.
- No Windows validation, no full repository suite, no end-to-end 40–60 minute high-resolution recording.
- Source pixel spot-check is **not** exhaustive when samples exceed the configured budget. It cannot prove card identity or OCR correctness.
- Existing ROI pixel auditor redecodes source frames from the beginning and may be slow on long recordings.

## Next

Measure memory/time of real-resolution synthetic 4-table recordings; optimize batch frame decoding without weakening SHA/PTS checks. Then link visual evidence to human-verified hand reconstruction.
