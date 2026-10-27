# Cycle 144 — explicit reviewed-PTS re-export gate (2026-10-27)

## Scope
Offline/async PLO5/PLO6 recorded sessions only. No live integration, playable poker tables, opponents, bets, credential changes, paid services or GitHub Actions. Consult `docs/VIDEO_ANALYZER_SCOPE.md`.

## Added
- `offline_reviewed_pts_reexport.py`: separate `prepare` and `export` CLI commands. `prepare` regenerates the Cycle-143 second-review plan from the original recording, PTS proposals and pipeline evidence, then emits a **create-only, default-deny** third-stage approval template for one accepted hand. `export` requires three explicit self-declared review flags, a reviewer label and `approved_for_export=true`. It rejects edited immutable fields, stale/tampered plan, source or pipeline artifacts, duplicate JSON keys, symlinks and existing output paths.
- Reuses the existing validated Monte Carlo/EV report and the original `offline_reviewed_math_clip_export` FFmpeg export path. A temporary directory is used for staging; the new MP4, SRT, JSON and `.audit.json` are hard-linked create-only, rolling back newly linked files on failure. Original clips, math reports, annotations and manifests are not modified.
- The audit binds source video SHA-256, plan SHA-256, separate approval SHA-256, original/new clip hashes and corrected timestamps. Reviewer labels and flags are **claims, not authentication**; no OCR/video-content verification or new Monte Carlo is performed.
- `test_offline_reviewed_pts_reexport.py`: 15 synthetic tests including real FFmpeg MP4 export, blocked/unapproved cases, tampering and overwrite guards.

## Local verification
- `python -m unittest -v test_offline_reviewed_pts_reexport.py test_offline_reviewed_pts_second_review.py test_offline_reviewed_pts_correction_import.py test_offline_reviewed_pts_contact_sheet.py test_offline_reviewed_source_pts_audit.py test_offline_reviewed_decision_timeline.py`
- **132 tests passed, 0 skipped** using bundled synthetic fixtures and local FFmpeg/FFprobe; full repository suite and GitHub CI not executed. The new tests skip if the external synthetic fixture is absent; it is not checked into GitHub.
- Synthetic 3.0s H.264 MP4 with `mov_text` subtitle track was produced. The corrected **decision timestamp** changed from 2.00s to 2.03s in the JSON report, but the clip start/end stayed 1.00s–4.00s; therefore the new MP4 bytes were identical to the original in this fixture. This is expected and **not** proof of visually changed video content.
- Original mathematical estimates were reused; Monte Carlo was not rerun.

## CLI usage
From `video_analyzer`, with all inputs in one offline session workspace:

```sh
python offline_reviewed_pts_reexport.py prepare source.mp4 review_corrected/review_template.json proposed_corrections.json second_review.json timestamp_plan.json PLO5_results new_export_approval.json PLO5_results PLO6_results
# Human inspects frames and assumptions, then edits the new approval JSON.
python offline_reviewed_pts_reexport.py export source.mp4 review_corrected/review_template.json proposed_corrections.json second_review.json timestamp_plan.json new_export_approval.json reexport_hand42 PLO5_results PLO6_results
```

## Not verified / blockers
- No authorized 3–5-minute annotated real PLO5/PLO6 recording. OCR, action/card recognition, hand segmentation and four-table 40–60-minute throughput remain unvalidated.
- The review label is not authenticated; mathematical range assumptions and visual poker facts are not independently checked.
- No complete repository test run or remote CI verification in this cycle.
