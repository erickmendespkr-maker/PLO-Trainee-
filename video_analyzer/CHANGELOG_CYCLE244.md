# Cycle 244 — human-reviewed temporal layouts and timestamp locator

**Scope:** offline/asynchronous recorded PLO5/PLO6 only. No live integration, betting, playable tables or AI opponents.

## Added
- `offline_table_temporal_review.py`: creates an unapproved editable draft from temporal FFmpeg evidence; human-supplied segment boundaries, stable table-ID claims and crop geometry; explicit confirmation flag; re-evaluates sampled frames before publishing; records SHA-256 provenance and note; rejects noncontiguous segments, overlaps, unsafe files and collisions.
- `Bounded visual FFmpeg previews`: maximum 12 segments, 4 regions and 48 short MP4 previews; HTML index and SHA-256 ledger; no full-session export or strategy verdict.
- `offline_temporal_decision_locator.py`: resolves a decision timestamp to a human-claimed table region, but blocks within a configurable 0.25-second guard of segment boundaries. Does not authorize OCR, equity or EV.
- 22 synthetic tests for temporal review and 19 pure synthetic tests for the locator.

## Synthetic demo
A 6-second 320x180 artificial recording changes its dividing lines around t=3s. Two human-*simulated* reviewed segments produce eight 1-second MP4 previews. Locator samples at 1.0s/4.0s resolve geometry claims; samples at 2.9s/3.1s are blocked near the transition.

## Verification and caveats
The 22 review tests and 19 locator tests passed locally; the 22 include an eight-MP4 FFmpeg export. Existing temporal/proposal tests were run in a separate prior cycle; the full repository test suite was **not** run. No real PLO recording was supplied; the confirmation flag in the demo is a **synthetic simulation**, not actual human review. No table identity, transition instant, OCR accuracy, EV or Windows compatibility is proven.

## Usage
```sh
python offline_table_temporal_regions.py session.mp4 evidence --interval 10
python offline_table_temporal_review.py template session.mp4 evidence/temporal_regions.json review_draft.json
# HUMAN: inspect the source video, edit segments, boundaries, coordinates and reviewer_note.
mkdir reviewed previews
python offline_table_temporal_review.py approve session.mp4 evidence/temporal_regions.json review_draft.json reviewed --confirm-reviewed
python offline_table_temporal_review.py previews session.mp4 reviewed/temporal_review.json previews
python offline_temporal_decision_locator.py session.mp4 reviewed/temporal_review.json T1 42.5
```

## Next
Integrate locator into decision-to-clip selection so clips crossing a region transition are rejected or explicitly split; add manual evidence by street; validate OCR on an authorized annotated 3–5-minute real PLO recording.
