# Cycle 269 — joint pixel/OCR provenance gate (offline)

## Scope
Read `docs/VIDEO_ANALYZER_SCOPE.md`. Only recorded, user-authorized PLO5/PLO6 sessions; no live assistance, playable tables, betting integration or AI opponents.

## Added
- `offline_joint_pixel_ocr_audit.py`: runs the existing independent `offline_region_sample_pixel_audit` and `offline_verified_ocr_benchmark` sequentially on the **same** recording, region bundle, original OCR report and supplied labels. Verifies their statuses, recording/manifest hashes, identical crop coverage, non-promotion flags, and re-hashes all input and PNG evidence before publishing three reports in a new directory. Fails closed on inconsistent, changed or tampered evidence.
- `test_offline_joint_pixel_ocr_audit.py`: 16 self-contained synthetic tests generating a four-region MP4 with FFmpeg. Includes a CLI smoke test, a changed video, a crop swap with recalculated SHA, bad labels, conflicting audit results, unsafe promotion, missing tools, symlinks, duplicate JSON keys and create-only behavior.

## Local verification (2026-11-01)
- Python 3.13.5; FFmpeg/FFprobe 7.1.5; Tesseract 5.5.0; Pillow.
- **68/68 selected tests passed**: 16 new + 12 region pixel audit + 16 OCR bridge + 24 recognition benchmark tests.
- A separate previously generated synthetic four-table video/PNG/OCR bundle from Cycle 267 was processed through the new joint CLI: one independent source frame and four table crops verified. The original OCR proposal values (`12`, `23`, `34`, `45`) were independently reproduced by running FFmpeg and Tesseract on the four synthetic ROIs during this cycle.
- Git blob SHA of published Python files checked against the exact local tested versions.

## Boundaries / not verified
- The **original** `offline_four_table_sample_review.build` and `offline_four_table_ocr_proposals.scan` were **not executed together** in this cycle; the joint gate consumes their compatible outputs. OCR test fixtures are synthetic; their label agreement does **not** measure real poker recognition.
- Human labels are not authenticated, table regions are manually declared, and raw OCR does not become verified cards/actions or equity/EV input.
- No real 3–5 minute annotated recording; no full 40–60 minute session, Windows, hand reconstruction, Monte Carlo/EV, or MP4 clip pipeline was tested.
- The publication directory is checked to be new before `os.rename`; concurrent external filesystem races are not guaranteed to be prevented on every platform. Run in a trusted local work directory.

## Next
Execute the original four-table sample builder and OCR scanner on a generated video in one test process; feed their actual outputs to this gate, then connect verified temporal hand-boundary evidence and human review. Continue synthetic tests until a licensed annotated poker video is available.

## CLI
`python video_analyzer/offline_joint_pixel_ocr_audit.py recording.mp4 region_bundle original_ocr.json human_labels.json new_audit_dir`

The generated `joint_report.json`, `pixel_audit.json` and `ocr_agreement.json` are diagnostic only. All authorization flags remain false.
