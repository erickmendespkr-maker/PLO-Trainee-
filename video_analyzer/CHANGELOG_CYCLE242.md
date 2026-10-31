# Cycle 242 — auditable offline manual table-region corrections

Scope: `docs/VIDEO_ANALYZER_SCOPE.md`; recorded PLO5/PLO6 only. No live poker access, playable tables, automatic OCR authorization, or strategy verdicts.

## Added
- `offline_table_region_corrections.py`: create a draft JSON from an unverified FFmpeg proposal; after explicit human review, accept corrected coordinates and a written reason. The proposal is revalidated by recomputing its sampled evidence against the exact video, preview and proposal hashes.
- Apply checks stable table IDs/order, 1–4 regions, even dimensions, in-frame bounds, no overlap, a meaningful change, a reviewer note, and an explicit `--confirm-reviewed` gate.
- Produce a crop-exporter-compatible `manual_layout.json`, `correction_audit.json` with before/after coordinates and SHA-256 links, and `corrected_preview.png`. Reject output collisions and symlinks; clean up partially published files on failure.
- `test_offline_table_region_corrections.py`: 15 synthetic tests for accepted correction, provenance, invalid geometry, forged JSON, output protection and confirmation.

## Usage
```bash
mkdir -p review corrected
python video_analyzer/offline_table_region_proposals.py propose recording.mp4 review
python video_analyzer/offline_table_region_corrections.py template recording.mp4 review/proposals.json review/correction_draft.json
# Review the recording and review/preview.png; edit only regions and reviewer_note in correction_draft.json.
python video_analyzer/offline_table_region_corrections.py apply recording.mp4 review/proposals.json review/correction_draft.json corrected --confirm-reviewed
# corrected/manual_layout.json is accepted by offline_ev_table_crop.py.
```

## Local verification
- 15/15 new synthetic tests passed with FFmpeg/FFprobe on Linux.
- 35/35 selected tests passed (15 new, 19 prior proposal tests, 1 prior proposal-to-crop integration test).
- Additional synthetic integration exercised corrected layout -> four cropped MP4 -> combined HTML with eight video elements; one correction recorded. Confirmation was **simulated in tests**, not performed by a person.
- GitHub-published Python source and tests matched the local tested Git blob hashes.

## Limitations and blockers
- A CLI confirmation flag is not proof of human inspection. Manual corrections do not verify that rectangles are poker tables.
- Tracking moving tables, real OCR accuracy, 40–60 minute processing, Windows execution, and complete repository tests are not validated.
- Authorized annotated 3–5 minute poker recording remains unavailable; continue synthetic/offline work.
