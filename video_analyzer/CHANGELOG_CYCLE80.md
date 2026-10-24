# Cycle 80 — PTS-audited manual table ROI OCR

Scope: offline/async recorded PLO5/PLO6 sessions only. No playable tables, live capture, opponents, betting, or platform integration.

## Implementation
- Added `activity_math_review_crop_ocr.py` to bridge the Cycle 78 table navigation PNGs and Cycle 79 decoded PTS audit with manually configured table/field ROIs.
- Re-runs both upstream FFmpeg crop export and decoded-PTS audit before accepting their reports; checks hashes and pixel-identical regenerated crops.
- Runs FFmpeg ROI cropping and Tesseract TSV OCR with a strict budget (default 64 tasks), outputting raw text, uncalibrated OCR confidence, and parsed **candidates** only.
- Preserves table ID, human-assigned but unverified hand references, requested seek, audited decoded filtergraph PTS when available, and SHA-256 provenance.
- Invalid ROIs, forged upstream reports, altered PNGs, symlinks, output overwrite, and excessive OCR work are rejected. All results remain unverified and barred from EV/equity/automatic clip decisions.

## Usage

```sh
python video_analyzer/activity_math_review_crop_ocr.py \
  recording.mp4 frames_dir handoff.json triage.json packet.json timeline.json \
  regions.json table_stills_dir pts_audit_dir manual_rois.json crop_ocr_dir
```

Manual ROI example (pixel coordinates **inside each table crop**, not the full video):

```json
{"schema_version":1,"rois":[
  {"table_id":1,"field":"pot","x":0,"y":0,"width":80,"height":60},
  {"table_id":2,"field":"pot","x":0,"y":0,"width":80,"height":60}
]}
```

Fields: `pot`, `bet`, `board`, `hero_cards`. No card or action is verified by an OCR candidate. Regions must be reviewed and calibrated on an authorized real recording.

Output: `crop_ocr_dir/math_review_crop_ocr.json`.

## Verification (local synthetic only)
- 6 new tests passed, covering four tables, real FFmpeg/Tesseract invocation, source hashes, invalid/duplicate ROI, task budget, forged PTS report, altered crop, symlink, CLI, and no mathematical authority.
- 44 focused integration tests passed, including the new tests and preceding review-frame, crop, PTS, handoff and triage components.
- Full-suite attempt did not complete within execution limit; no full-suite pass is claimed.
- No real poker recording was supplied. Synthetic test frames do not establish recognition accuracy or hand reconstruction.

## Next
Add calibrated field-specific ROI profiles from an authorized sample, quantify OCR precision/recall against human labels, and preserve uncertain observations for manual reconstruction before any math/clip authorization.
