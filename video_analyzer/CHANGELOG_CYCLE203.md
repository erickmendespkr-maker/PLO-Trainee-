# Cycle 203 — Human-configured ROIs, candidate review and FFmpeg clip bridge

## Scope
Branch: `feature/plo5-plo6-training`. Only recorded offline PLO5/PLO6 sessions. No playable tables, live poker connections, credentials, paid services, or changes to `main`.

## Delivered
- `offline_manual_roi_review.py` adds a CLI to analyze up to four **human-configured, non-overlapping normalized rectangles**, using the existing FFmpeg/FFprobe timeline sampler. Stores actual selected-frame PTS, per-table activity events, source pixel rectangles, video SHA-256 and ROI configuration SHA-256.
- The same module accepts an explicit review decision for a candidate window: `confirmed_hand`, `not_hand`, or `uncertain`. Only `confirmed_hand` with human-supplied hand ID and boundaries enters a JSON clip plan. The plan records video, timeline and review input hashes; no automatic hand boundary is asserted.
- `offline_review_plan_clip_bridge.py` connects that plan to the **existing** `offline_reviewed_clip_export.py`, requiring a separate human-authored explanation per hand. The exporter crops each table ROI, re-encodes MP4 with FFmpeg, writes a JSON sidecar, and emits a manifest of clip hashes. New output directory only; staged files are not published on failed export. Existing exporter does not include audio.

## Reproduce
From `video_analyzer`, with FFmpeg/FFprobe on PATH:

```sh
python offline_manual_roi_review.py analyze recording.mp4 rois.json NEW_timeline.json
python offline_manual_roi_review.py review recording.mp4 NEW_timeline.json decisions.json NEW_plan.json
python offline_review_plan_clip_bridge.py recording.mp4 NEW_plan.json NEW_timeline.json explanations.json NEW_clips_directory
python -m unittest -v test_offline_four_table_visual_timeline.py test_offline_manual_roi_review.py test_offline_review_plan_clip_bridge.py
```

Example `rois.json`:

```json
{"schema_version":1,"tables":[{"table_id":"table_1","normalized_rect":[0,0,0.5,0.5]},{"table_id":"table_2","normalized_rect":[0.5,0,0.5,0.5]},{"table_id":"table_3","normalized_rect":[0,0.5,0.5,0.5]},{"table_id":"table_4","normalized_rect":[0.5,0.5,0.5,0.5]}]}
```

Example `decisions.json`: `{"schema_version":1,"reviews":[{"table_id":"table_1","candidate_index":0,"decision":"confirmed_hand","hand_id":"H001","start_seconds":1.2,"end_seconds":3.4}]}`. `explanations.json`: `{"explanations":{"H001":"Intervalo revisado manualmente; cartas e ações ainda não verificadas."}}`.

## Local verification
- New ROI/review tests: **19** cases; new clip-bridge-specific tests: **7** cases. Combined selected invocation: **84 test executions passed** (includes inherited/rediscovered tests, not 84 unique scenarios).
- A synthetic 12-second, 320×192, four-quadrant FFmpeg fixture was generated inside the tests. Independent activity changes at selected source PTS 2, 4, 6, 8 seconds were detected. One human-declared synthetic interval produced a cropped MP4, JSON sidecar and manifest with SHA-256 checked.
- No GitHub Actions. The local container ran FFmpeg, FFprobe and Python unittest. This is not the full repository suite.

## Limitations and blockers
- No authorized, annotated 3–5 minute real session has been provided; OCR, hand segmentation precision, equity/EV accuracy for reconstructed hands, Windows behavior and 1080p/30 FPS throughput remain **unverified**.
- Manual ROIs are supplied as JSON, not yet a visual drag-and-drop editor. Crops must have even pixel coordinates/dimensions for the existing exporter. This workflow does not infer hidden cards or actions.
- Human confirmation is a declaration, not independent visual proof. Unreviewed candidates are unknown, not rejected hands. MP4 clip exports have no audio in this MVP.

## Next
Build a browser-based offline ROI selector and candidate review UI, preserving source PTS and hashes. Then connect reviewed hand metadata to mathematical reports while refusing EV conclusions for missing observations.
