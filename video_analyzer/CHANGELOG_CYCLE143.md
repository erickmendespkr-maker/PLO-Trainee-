# Cycle 143 — second-stage PTS review and multi-codec synthetic regression (2026-10-27)

## Scope and safety
Only offline recorded MP4/WebM. No playable tables, live poker integration, betting actions, opponents, production changes, credentials, paid services, or GitHub Actions. This is **not** a visual poker-recognition result.

## Added
- `offline_reviewed_pts_second_review.py`: `prepare` produces a new, editable second-stage review JSON from a Cycle-142 proposed-corrections report. It revalidates the source video SHA-256, decoded-frame PTS, Cycle-141 reference JPEG hashes, and existing pipeline artifacts. It binds the original proposal SHA-256 and individual pipeline-manifest SHA-256 values into the review template.
- `finalize` accepts only explicitly marked review decisions with all three manual review flags (source frames, clip windows, math provenance), a reviewer *label* and bounded notes. The reviewer label and flags are **self-declared and not authenticated**. The result is a **non-exportable timestamp plan**, not a new annotation or permission to regenerate MP4.
- The second stage rejects changed evidence fields, duplicate JSON keys, source/report/manifest tampering, symlinks, unsafe paths, existing output files, mixed approvals within a single hand, and timestamp windows that extend outside the previously approved clip interval. Source MP4, previous MP4s, mathematical results, and historical annotations remain untouched.
- `test_offline_reviewed_pts_second_review.py`: 20 new synthetic test cases. A regression test found that appending whitespace to `pipeline.json` was not detected by semantic-only comparison; fixed by binding exact manifest bytes in the second-stage template.
- `test_offline_reviewed_pts_multicodec_synthetic.py`: two additional FFmpeg/FFprobe tests covering H.264 constant frame rate and VP9 WebM with dropped frames/variable frame rate. Four *visual regions* are synthetic color overlays, not detected poker tables.

## Reproduction
From `video_analyzer` with Python and FFprobe installed:

```sh
python -m unittest -v test_offline_reviewed_pts_second_review.py test_offline_reviewed_pts_multicodec_synthetic.py test_offline_reviewed_pts_correction_import.py test_offline_reviewed_pts_contact_sheet.py test_offline_reviewed_source_pts_audit.py test_offline_reviewed_decision_timeline.py
python offline_reviewed_pts_second_review.py prepare source.mp4 review_corrected/review_template.json proposed_corrections.json second_review.json PLO5_results PLO6_results
# A human reviews the source and edits second_review.json. Flags are claims, not identity proof.
python offline_reviewed_pts_second_review.py finalize source.mp4 review_corrected/review_template.json proposed_corrections.json second_review.json timestamp_plan.json PLO5_results PLO6_results
```

- Local selected suite: **119 tests passed** (22 new, 97 prior) with synthetic fixtures and FFmpeg/FFprobe. No tests were skipped.
- Additional standalone 12-second synthetic 640×360 benchmark: H.264 MP4 144 frames / 0.094s FFprobe scan; VP9 VFR WebM 36 frames / 0.109s FFprobe scan. These are single local measurements, not performance promises. A timestamp of 11.5s in VFR mapped to PTS 11.333s, **0.167s away**, which must be treated as outside the 0.15s tolerance.
- Synthetic demonstration: one claimed second-stage review changed a PLO5 decision timestamp from 2.00s to 2.03s while keeping its original 1.00–4.00s clip bounds; the resulting plan has `approved_for_export=false`.

## Not verified / blockers
- The complete repository test suite and GitHub remote CI were not run. A real end-to-end MP4 re-export using corrected timestamps was **not** performed.
- There is no authorized annotated 3–5-minute PLO5/PLO6 recording to calibrate OCR/vision or verify hand reconstruction, card/action recognition, and decision timestamps. Long 40–60-minute sessions with four actual tables remain unverified.
- The second-stage review does not authenticate the reviewer, verify visible poker content, recalculate Monte Carlo equity/EV, or validate the assumed opponent ranges. A separate explicit annotation/export step must revalidate mathematical and video provenance before producing new clips.
