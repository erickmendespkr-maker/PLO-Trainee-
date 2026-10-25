# Cycle 85 — human review handoff for OCR hand-boundary candidates

Scope: `docs/VIDEO_ANALYZER_SCOPE.md`. Offline/asynchronous recorded-video analysis only. No playable poker tables, AI opponents, live poker integration, wagering, credentials, or paid services.

## Implemented

- Added `activity_boundary_review_handoff.py`: a JSON human-review queue linking Cycle 82 OCR boundary candidates, Cycle 83 navigation PNGs and Cycle 84 FFmpeg decoded-PTS audit.
- The handoff **repeats** the bounded Cycle 84 FFmpeg audit (at most 120 frames) and requires exact equality with the supplied audit JSON. The upstream audit revalidates source SHA-256, OCR boundary plans, navigation images, ROI configuration and byte-identical decoded-PTS claims.
- Review tasks preserve table identity (up to four tables), candidate windows, signal kinds, ambiguity flags, frame hashes, requested seek times and decoded PTS only where the re-decode matched. Tasks without images remain pending when the extraction budget was reached.
- `template` creates a deliberately incomplete human annotation form. `annotate` accepts `confirmed_transition`, `rejected_transition` or `uncertain`; a reported confirmation requires a timestamp inside the candidate interval and a frame from that same task.
- All outputs retain false flags for independently verified hands, cards/actions, equity/EV readiness, strategic errors and automatic clip selection. A human label is not independent poker verification.

## CLI

```sh
python video_analyzer/activity_boundary_review_handoff.py packet session.mp4 temporal.json boundary.json ./navigation ./pts_audit/boundary_pts_audit.json ./review_packet.json --regions regions.json
python video_analyzer/activity_boundary_review_handoff.py template ./review_packet.json ./annotation_form.json
# Human fills verdict/reviewer/timestamp/frame_ids/notes and removes unreviewed entries.
python video_analyzer/activity_boundary_review_handoff.py annotate ./review_packet.json ./completed_form.json ./review_labels.json
```

Omit `--regions` when the original evidence had no crop profile. Every output path must be new. The packet references PNG filenames relative to the navigation directory.

## Local verification (2026-10-24)

- Five new synthetic tests passed: four-table separation, repeated FFmpeg audit, tampering rejection, reviewer labels, timestamp/frame requirements and overwrite refusal.
- Selected upstream/integration tests passed; see the cycle log for the final count.
- Synthetic demonstration: four-table recording and one **synthetic** uncertain annotation, not real poker or genuine human validation.
- Not verified: full-suite success, remote CI, real PLO5/PLO6 OCR accuracy, full 40–60 minute sessions, video-derived equity/EV or automatic MP4 highlights.

## Remaining blocker

An authorized 3–5 minute PLO5/PLO6 recording with human ground truth is required to benchmark OCR, transition precision/recall and the subsequent mathematical review. Next: link reviewed boundaries to structured hand-history candidates without promoting OCR guesses or reviewer claims to verified strategic facts.
