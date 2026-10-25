# Cycle 90 — action-timestamp stills with independent FFmpeg PTS audit (2026-10-25)

Scope: `docs/VIDEO_ANALYZER_SCOPE.md`. Only offline user-uploaded PLO5/PLO6 videos; no live play, real poker integration, credentials, hosting or spending.

## Implemented

- `hand_action_pts_evidence.py` revalidates the original navigation and manual-review report, checks video SHA-256, and plans bounded frame requests only for human-confirmed fields/actions with source timestamps. Unknown values and hypotheses never become evidence.
- Up to four tables with **mandatory manually specified rectangles when more than one table is represented**; maximum 120 PNGs per invocation, 60 by default. Deduplicates repeated timestamps per table and reports skipped requests.
- FFmpeg extracts a PNG at each requested timestamp; an independent second decode must produce identical PNG bytes, filtergraph PTS and time base before a decoded PTS is reported. A further 0.25-second tolerance determines whether the frame is near the requested timestamp.
- Rehashes all source inputs after extraction; output directory is create-only, with an audit JSON and SHA-256 for each PNG. Every strategic/math authority flag remains false.
- `test_hand_action_pts_evidence.py` covers synthetic FFmpeg, four tables, budget, hypotheses, malformed reports, SHA mismatch, symlinks, PTS failure, and second-decode mismatch.

## Local verification

- 15 new tests passed (plus 4 parameterized subtests).
- 79 selected tests passed (plus 10 parameterized subtests) in 16.26 seconds, including upstream navigation, review, visual boundary, and PTS audits. The 79 include the 15 new tests.
- Tests use a generated four-second MPEG-4 synthetic recording, not a real poker session. The full suite, remote CI, 40–60 minute performance, card OCR accuracy, equity/EV and end-to-end explanatory MP4 output are **not verified**.

## Usage

```sh
python video_analyzer/hand_action_pts_evidence.py recording.mp4 navigation.json reviewed_hand_report.json new_action_evidence_dir --regions-json table_regions.json --max-frames 60
```

`table_regions.json` maps table IDs `"1"` through `"4"` to `{x,y,width,height}`. No regions are required for a single table. The reviewed hand report is validated for schema/semantics against the navigation, but **not cryptographically signed by a reviewer**. A byte-matched PNG proves neither the claimed card/action nor the accuracy of the original human annotation. A nearby decoded PTS is not the requested seek PTS or a wall-clock timestamp.

## Blocker / next

An authorized 3–5 minute PLO5/PLO6 sample with independent hand annotations is still needed. Next: build a review interface/report linking these audited action stills back to their individual field/action references, then evaluate recognition against labeled real video. No math or clip authority should be inferred from stills alone.
