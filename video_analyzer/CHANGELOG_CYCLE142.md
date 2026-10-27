# Cycle 142 — offline human PTS correction importer (2026-10-27)

## Added
- `offline_reviewed_pts_correction_import.py` reads a human-edited Cycle-141 `review_template.json` and produces a **new, unapproved** JSON report of proposed timestamp corrections. No pipeline annotation, math report, source recording, or MP4 is overwritten.
- Rechecks the actual MP4/WebM SHA-256, all pipeline manifests and artifacts, the original PTS audit, the contact-sheet reference metadata and JPEG hashes. Rebuilds the original review-point list and rejects modifications to immutable evidence fields. Only `corrected_seconds` and `approved_by_human` may change per review point.
- For each proposed correction, runs a new FFprobe decoded-frame scan, records nearest source-frame PTS and index, requires <=0.15 s frame proximity, <=5 s correction shift, and keeps decision/start/end within the previously approved clip interval. Corrections remain **proposals** even when the template's human-review flag is true; reviewer identity and visual correctness are not authenticated.
- Strict JSON duplicate-key/nonfinite rejection, symlink/path restrictions, create-only output and output-size bounds. No automatic export or reapproval; no live poker integration.

## Reproduce (FFprobe required)
From `video_analyzer`:

```sh
python -m unittest -v test_offline_reviewed_pts_correction_import.py test_offline_reviewed_pts_contact_sheet.py test_offline_reviewed_source_pts_audit.py test_offline_reviewed_decision_timeline.py
python offline_reviewed_pts_correction_import.py source.mp4 reference_review/review_template.json new_proposals.json PLO5_results PLO6_results
```

- Local selected suite: **97 passed** (29 new, 68 regression) in 7.986 s, using synthetic recordings and existing repository test fixtures.
- Demonstration: edited synthetic reference review has one human-flagged proposal of 2.03 s, mapped to decoded PTS 2.00 s at frame #20, without clip approval. No real poker video or OCR validation.

## Known limitations
- Human-review flag is not authenticated; the output is intentionally not an approved pipeline input.
- Corrected timestamps are only tested against decoded frame proximity and previously approved time windows; they do not prove visible cards, action, or hand boundaries.
- The full repository suite, real PLO5/PLO6 videos, and long four-table sessions were not tested here. Source footage with variable frame rate/codecs still needs validation.
- Next: explicit second-stage reviewer approval and provenance binding to re-export, plus multi-codec synthetic benchmarks and real annotated video once provided.
