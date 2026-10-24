# Cycle 71 — Offline OCR ↔ reviewed hand timeline (review only)

## Scope
Added `activity_ocr_timeline_review.py` to compare unverified OCR candidates with human-reviewed visible hand observations. The adapter uses only offline artifacts, never gameplay, betting, hidden-card guesses, or live integrations.

## Inputs and CLI

```bash
python video_analyzer/activity_ocr_timeline_review.py \
  ocr_candidates.json reviewed_timeline.json comparison.json \
  --alignment-json reviewer_alignment.json
```

An alignment file is **optional**, but without it the report refuses to link any OCR candidate to a reviewed observation, even when numeric timestamps coincide. Its required fields are:

```json
{
  "schema_version": 1,
  "recording_sha256": "<same 64-character SHA-256 in both reports>",
  "ocr_timestamp_semantics": "decoded_filtergraph_pts_not_capture_time",
  "timeline_timestamp_semantics": "decoded_filtergraph_pts_not_capture_time",
  "reviewer_confirmed_same_recording_pts_origin": true,
  "ocr_pts_minus_timeline_pts_seconds": 0.0,
  "reviewer_note": "Human explanation of how clocks were aligned"
}
```

The tool requires the same recording digest, validates upstream statuses and provenance, compares same-table/same-field observations at timestamps rounded to six decimal places, detects disagreements with reviewed labels and conflicting OCR candidates at the same timestamp. It never promotes OCR confidence to correctness probability, labels to verified facts, or temporal coincidences to hand boundaries. It refuses to overwrite output JSON.

## Verification
- 8 new synthetic tests passed locally.
- 52 selected integration tests passed locally (including the 8 new tests).
- Full repository suite was attempted but exceeded the execution timeout; **no complete-suite pass is claimed**.
- Synthetic test data are not evidence of accuracy on real poker footage.

## Blocker and next step
An authorized 3–5 minute PLO5/PLO6 recording is needed to calibrate OCR regions, align PTS clocks and measure accuracy against manually annotated hands. Continue synthetic consistency and OCR provenance tests without it. Do not authorize equity/EV or clips from unverified OCR output.
