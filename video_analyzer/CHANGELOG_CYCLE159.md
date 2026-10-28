# Cycle 159 — Offline hand-to-clip provenance links

Scope: `docs/VIDEO_ANALYZER_SCOPE.md`; target branch `feature/plo5-plo6-training` only. No live poker, playable tables, credentials, production changes or paid services.

## Implemented

- `offline_reviewed_clip_hand_links.py`: new offline, fail-closed **consistency audit** linking an existing hand-candidate JSON to a manually approved clip batch (up to 12 selections, tables 1–4).
- Rechecks source video SHA-256, candidate source SHA, batch manifest SHA, batch report identity, each clip's SHA, request SHA, sidecar fields, hand/table ID, crop metadata, timestamps and explicit reviewer flags.
- Requires each clip to contain the full human-declared hand window, with no more than 15 seconds padding on either side. Rejects missing/duplicate hand IDs, mismatched tables, tampered video/clips, symlinked batch members, traversal paths, duplicate JSON keys, nonfinite timestamps, existing outputs and stale manifests.
- Optional attachment of previously generated *conditional equity* bridge reports, only when their recording/candidate hashes and reviewed hero/board observations agree. Does not independently recompute Monte Carlo or authenticate the approval; reports that explicitly.
- Produces a **new** JSON provenance report; no changes to source MP4, exported clips or original batch reports. No EV attachment or automatic clip selection is authorized.

## Tests performed locally (not GitHub Actions)

- `python -m unittest -v test_offline_reviewed_clip_hand_links.py test_offline_reviewed_clip_hand_links_ffmpeg.py`: **24 passed** (23 synthetic schema/tamper cases and one FFmpeg integration test).
- The integration test generates a 4-second **non-poker** 640x360 synthetic MP4, extracts four 320x180 H.264 crops (2 seconds each), validates their duration and dimensions with FFprobe, links the four hand-candidate IDs and checks tampering rejection.
- `python -m py_compile` completed for both implementation and tests.
- Tests do **not** validate real poker hands, OCR, actual reviewed observations, equity accuracy, EV, throughput on 40–60 minute recordings or the full repository test suite.

## Usage

```sh
python video_analyzer/offline_reviewed_clip_hand_links.py \
  recording.mp4 hand_candidates.json batch_manifest.json \
  exported_batch_directory new_link_report.json \
  --equity optional_reviewed_equity_report.json
```

The report status is `offline_clip_hand_provenance_links_only`. `video_evidence_verified`, `equity_authenticity_verified`, `ev_verified`, `automatic_clip_selection_authorized` and `action_recommendation_authorized` remain **false**.

## Blockers and next cycle

An authorized, annotated 3–5 minute PLO5/PLO6 recording is still missing. Continue by attaching EV only through a separately reviewed, mathematically valid decision record and adding complete end-to-end tests for actual OCR outputs. Do not infer hidden cards or call model-dependent EV a definitive mistake.
