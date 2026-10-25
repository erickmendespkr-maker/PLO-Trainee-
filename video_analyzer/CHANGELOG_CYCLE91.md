# Cycle 91 — offline review gallery for audited action stills (2026-10-25)

Scope: `docs/VIDEO_ANALYZER_SCOPE.md`. Only user-provided, recorded PLO5/PLO6 sessions. No live assistance, playable tables, real poker integration, credentials, hosting or spending.

## Implemented

- `hand_action_review_gallery.py` links manually reviewed fields/actions to the **action-timestamp stills** from Cycle 90, separately for up to four tables.
- Re-derives the expected frame plan from the original video, navigation report, reviewed hand report, and optional manually supplied table rectangles. Validates input SHA-256 provenance, audit manifest schema, frame IDs, associations, skipped requests, count totals, decoded filtergraph PTS/time-base arithmetic, near-frame tolerance and PNG bytes.
- Outputs a create-only directory containing `review_gallery.json` and a **local static** `review_gallery.html`. The HTML references the existing PNGs via relative paths; no video/image upload, third-party scripts, network calls, copies of the video or automated poker analysis.
- Distinguishes unknown, hypothesis, unconfirmed manual claim, skipped-by-budget, unusable PTS and nearby audited frame. A nearby image remains an unverified human claim, **not** proof of cards/actions, hand boundaries, equity, EV, or errors.
- HTML escapes reviewer-provided annotation strings; rejects symlinked/missing/tampered PNGs, incompatible reports, forged authority flags, source changes and overwrite attempts.

## Verification

- 17 new synthetic tests passed.
- 69 selected local tests passed in 24.98 seconds (includes 17 new tests), covering action extraction, gallery, previous evidence linking, manual review and history bridge.
- An earlier, broader test selection did not finish within the execution window; it is **not** reported as passed. Full repository suite and remote CI are **not verified**.
- Tests use a generated 4-second, 320x240 MPEG-4 video with four manually supplied table regions; this is not real poker footage.

## Usage

```sh
python video_analyzer/hand_action_pts_evidence.py recording.mp4 navigation.json reviewed_hand_report.json new_action_evidence_dir --regions-json table_regions.json
python video_analyzer/hand_action_review_gallery.py recording.mp4 navigation.json reviewed_hand_report.json new_action_evidence_dir new_gallery_dir --regions-json table_regions.json
```

Open `new_gallery_dir/review_gallery.html` locally. Keep the `new_action_evidence_dir` at the same relative location after generation; the gallery does not duplicate images. For a single table, the regions argument can be omitted if the original audit also omitted it.

## Limitations and blocker

This stage checks the *existing* independent FFmpeg audit, but does **not** re-decode video during gallery generation or validate poker facts visually. SHA-256 checks establish local byte consistency, not a signed reviewer identity or trustworthy OCR. User-supplied annotations remain unverified. Missing: authorized 3–5 minute PLO5/PLO6 sample with hand labels to measure recognition quality. 40–60 minute sessions, complete hand reconstruction, integrated equity/EV and explanatory MP4 export are not verified end to end.

Next: introduce explicit per-field review decisions (confirmed/rejected/uncertain) linked to the gallery, without treating those decisions as mathematically sufficient; then integrate review confidence into scenario preparation for the existing equity/EV engine.
