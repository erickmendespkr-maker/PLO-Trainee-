# Cycle 86 — human boundary labels to navigation-only spans

Scope: `docs/VIDEO_ANALYZER_SCOPE.md`. Offline/asynchronous recorded PLO5/PLO6 analysis only; no playable tables, live poker integrations, AI opponents, credentials, payments or production changes.

## Published in this branch

- `boundary_history_bridge.py` links Cycle 85's evidence-bound review packet and human labels into **provisional** spans between consecutive human-reported transitions on the same table. It never infers hand identities, cards, actions, pot, equity, EV or strategic errors.
- Source packet SHA-256, per-table grouping, in-window timestamps, selected audited frames, duplicate task/label detection, overlapping transition rejection and conservative readiness flags are checked.
- The result is a navigation index, **not** a validated hand history. Unknown candidate transitions inside spans are not yet modeled by this minimal bridge; do not use it as a mathematical input.
- `test_boundary_history_bridge.py` contains six tests: five synthetic unit tests (four-table separation, rejected unaudited frames, incorrect source hash, overlapping windows and false authority claims) plus a real FFmpeg/PTS audit-to-review-handoff integration using synthetic frames.

## Local verification — 2026-10-24

- 6 tests for the **published** bridge passed (including synthetic FFmpeg integration).
- 137 selected regression/integration tests passed, including the 6 bridge tests and 20 tests of a separate local experimental boundary-draft module (not published in this branch).
- Full-suite discovery was attempted but exceeded 240 seconds. It is **not verified**.
- Real poker recognition, reconstructed hands, end-to-end MP4 clips, 40–60 minute throughput and remote CI are **not verified**.

## CLI

```sh
python -c "from video_analyzer.boundary_history_bridge import export; export('review_packet.json', 'review_labels.json', 'navigation_spans.json')"
```

Use only after the Cycle 85 human review handoff. Input labels remain subjective, even when their navigation frames have byte-matched FFmpeg PTS. The output is not eligible for equity/EV or automatic clip selection.

## Blocker / next

An authorized 3–5 minute recorded PLO5/PLO6 session and independent human hand annotations are still needed. Next: strengthen the published bridge with explicit pending/uncertain interior candidates, per-frame provenance, duplicate-key rejection, and formal hand-history review before any mathematical gating.
