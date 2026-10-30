# Cycle 220 — Offline FFmpeg/Tesseract OCR proposal extractor

Scope: `docs/VIDEO_ANALYZER_SCOPE.md`. Only recorded local videos; no live poker integration, no simulator, no paid APIs or GitHub Actions.

## Added

- `video_analyzer/offline_ffmpeg_tesseract_proposals.py`: local MP4/WebM + existing human-declared hand plan + manual normalized ROI/time sampling specification -> JSON OCR proposals compatible with `offline_ocr_review_bridge.py`. The program verifies the actual video SHA-256 against the plan, checks video geometry/duration using ffprobe, extracts crops with FFmpeg, runs Tesseract TSV, and records text, raw uncalibrated confidence, table, hand, timestamp and ROI.
- `video_analyzer/test_offline_ffmpeg_tesseract_proposals.py`: 18 synthetic tests including a four-table 3-second generated video, real FFmpeg+Tesseract extraction, hash mismatches, ROI/PTS/identity validation, safe new-file output, duplicate samples and the fail-closed mathematical queue invariant.

## CLI

```sh
python video_analyzer/offline_ffmpeg_tesseract_proposals.py recording.mp4 plan.json samples.json new_proposals.json
python video_analyzer/offline_ocr_review_bridge.py plan.json new_proposals.json new_worksheet.json new_annotations.json
```

Example `samples.json` (human-declared, normalized coordinates of the *full* video frame, not table-local coordinates):

```json
{
  "schema_version": 1,
  "status": "human_declared_offline_roi_samples",
  "samples": [
    {
      "hand_id": "H1", "table_id": "T1", "field": "hero_card", "slot": 0,
      "pts_seconds": 12.0,
      "roi": {"x": 0.1, "y": 0.2, "w": 0.12, "h": 0.08}
    }
  ]
}
```

The sample must refer to an existing hand in `plan.json`; the timestamp must fall within that hand and the video. Fields: `hero_card`, `board_card`, `pot`, `stack`, `action`, `variant`. Card fields require slot 0–5 for hero or 0–4 for board; other fields use `null`. At most 6000 samples, 3600 seconds, 8192 px per dimension and 8 GiB input. The extractor refuses existing output paths and symlink video files. Missing/invalid OCR text is skipped, not guessed.

## Safety and limits

This is **not** automatic hand segmentation, automatic ROI detection, action recognition, or a validated poker card OCR model. The user/reviewer supplies all hand boundaries, table IDs, ROI locations and sampling timestamps. Raw Tesseract confidence is uncalibrated; even a 100% OCR score cannot promote a card to confirmed status or initiate Monte Carlo. The downstream review bridge generates an unverified worksheet and blocked annotations, requiring independent human frame review before any mathematical calculation. The `source_video_sha256_claim` in the generated proposals is now measured from the local file, not merely copied from the plan.

The implementation uses subprocesses with explicit argument arrays, timeouts and no shell; it does not access any poker platform. FFmpeg seek time can be approximate for some codecs, so frame-exact timestamp accuracy and OCR recognition on real recordings remain **unverified**. It processes ROIs sequentially; performance on 40–60 minute recordings and Windows is unverified.

## Tests

Run `python -m unittest discover -p 'test_offline_*.py'` in `video_analyzer/` with FFmpeg, ffprobe, Tesseract, Pillow and DejaVuSans-Bold available. If these are missing, the integration fixture skips rather than falsely reporting recognition success.

Locally: 197 selected tests passed (18 new), using the Cycle 219 source/test snapshot and new files. A synthetic four-table video produced four OCR card suggestions (`As`, `Kd`, `Qh`, `Jc`), with zero hands promoted to equity. No real-session recognition accuracy was measured. Full repository suite and Windows remain untested. A permitted 3–5 minute human-annotated PLO5/PLO6 recording is still needed.
