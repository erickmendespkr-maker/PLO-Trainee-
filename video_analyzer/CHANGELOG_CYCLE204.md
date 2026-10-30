# Cycle 204 — offline visual reviewer prototype and review contract

Scope: branch `feature/plo5-plo6-training` only; recorded PLO5/PLO6 videos, no live poker integration, no playable tables, no credentials, no paid services.

## Published to GitHub
- `video_analyzer/offline_visual_review_contract.py`: verifies browser-generated `rois.json` and `decisions.json` against a timeline produced by the existing FFmpeg analyzer. Requires exact ROI table order, normalized rectangles, pixel rectangles, ROI configuration SHA-256, video SHA-256, and the existing manual review validation. Produces a new clip plan JSON, refusing to overwrite existing output.
- `video_analyzer/test_offline_visual_review_contract.py`: seven tests using locally generated FFmpeg black/white synthetic clips; covers valid input, ROI modification, table reordering, video hash mismatch, duplicate review, invalid hand boundaries, and no-overwrite behavior.

## Local prototype (in cycle ZIP; NOT YET published to GitHub)
- `offline_visual_review_ui.html`: standalone browser UI for opening a local recording, selecting up to four non-overlapping ROIs with the mouse, importing an FFmpeg timeline, seeking candidate windows, marking human decisions (`confirmed_hand`, `not_hand`, `uncertain`), entering manual boundaries and notes, and downloading JSON compatible with existing Python CLI. No external scripts or network calls.
- `offline_visual_review_ui.py`: a dependency-free generator that reconstructs the same HTML from a compressed asset, verifies its SHA-256, and writes a new file only.
- `test_offline_visual_review_ui.py`: 11 Chromium/Playwright browser tests including a generated review validated by the existing Python `review_plan` function. Chromium in this environment blocks direct `file://` navigation; the tests use `page.set_content` and file uploads. Thus direct `file://` opening is not verified.

## Verified locally
- 102 selected test executions passed, including prior timeline, manual ROI and clip bridge suites plus seven new contract tests and 11 browser UI tests. See `combined_tests.log` in the cycle ZIP.
- Synthetic 320x192, 12-second MP4 for the browser tests; independent FFmpeg fixtures generated for the new contract tests. These are not real poker sessions.
- The local HTML preview is in `offline_ui_preview.png`.

## Reproduce
From `video_analyzer` with FFmpeg/FFprobe installed:

```sh
python -m unittest -v test_offline_visual_review_contract.py
python offline_visual_review_contract.py recording.mp4 rois.json timeline.json decisions.json NEW_plan.json
```

For the local UI prototype, open `offline_visual_review_ui.html` in a browser, select a recording and export ROIs. Run `offline_manual_roi_review.py analyze`, import its timeline in the UI, review candidates, export decisions, then use the contract CLI. Keep the exact original ROI JSON file: the contract verifies its SHA-256.

## Not verified / blockers
- Local visual UI is not yet committed to GitHub; next cycle should publish the readable HTML and browser tests after independent review.
- Browser-side metadata comparison is not cryptographic video verification; Python performs the actual SHA-256 check. The HTML preview and browser tests are synthetic; Windows `file://` and real recordings are unverified.
- No authorized annotated 3–5 minute poker video is available. No claim of OCR accuracy, automatic hand boundaries, equity/EV validity for real hands, or one-hour 1080p throughput.
