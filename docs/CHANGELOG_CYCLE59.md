# Cycle 59 — conservative offline review triage

Scope: `docs/VIDEO_ANALYZER_SCOPE.md`. This addition neither plays poker nor connects to poker platforms.

## New code
- `video_analyzer/activity_review_triage_math.py`: read-only, fail-closed review-workload candidates. Revalidates source clip hashes and replays seeded hypothetical calculations through `build_explanations`.
- `video_analyzer/test_activity_review_triage_math.py`: synthetic FFmpeg-backed regression tests.

## Semantics
- **No strategic ranking, no automated clip selection, no error verdicts.** Results are sorted by source timestamp only.
- Incomplete human-reviewed fields produce `needs_evidence`.
- For a fully human-attested **call**, a call amount at least 25% of the pre-action pot produces `human_attention_suggested`; smaller calls produce `human_review_optional`. This is a simple review-attention heuristic, **not** equity, EV, mistake severity, confidence in visual recognition, or a recommendation to call.
- Monte Carlo results are merely flagged as present and the sampling CI is shown; neither CI nor conditional EV changes the review category. Confidence in video evidence and ranges remains explicitly **unverified**.
- Does not edit input MP4s or authorize export; output is a new JSON sidecar.

## CLI
From `video_analyzer`:

```bash
python activity_review_triage_math.py clip_manifest.json clips_dir worksheet.json request.json hypothetical_report.json new_triage.json
python -m unittest -q test_activity_review_triage_math
```

## Outstanding
- No authorized 3–5 minute PLO5/PLO6 sample, so real-video OCR, hand reconstruction and long-session performance remain unverified.
- No independent visual evidence audit; human attestation is not a verified observation.
- No real-hand EV or automatic strategic mistake detection. The attention threshold is heuristic and must not be presented as a poker strategy assessment.
