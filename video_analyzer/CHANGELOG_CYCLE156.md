# Cycle 156 — reviewed snapshot to conditional PLO5/PLO6 equity bridge

Branch: `feature/plo5-plo6-training`. Scope: `docs/VIDEO_ANALYZER_SCOPE.md`.

## Delivered

- New offline adapter `offline_omaha_reviewed_equity_bridge.py` takes an **incomplete** reviewed hand-candidates JSON, its action-timeline audit, and an explicitly human-approved JSON manifest.
- Recomputes the original action-timeline audit from the hand candidates and requires the supplied audit to match. Binds approval to both input SHA-256 hashes.
- Requires a selected **human-reviewed visible hero-hole observation** and **board observation**, valid hand/table, chronology and absence of unresolved visible card conflicts. It never supplies missing cards or action history.
- Validates the explicit opponent-combination hypothesis through the existing `offline_omaha_equity_mc.py` contract, then runs deterministic heads-up Monte Carlo equity.
- Output includes selected source observation indices, crop SHA-256 values, timestamps, seed, sample count, confidence interval and range hypothesis. Always sets `video_evidence_verified=false`, `complete_hand_reconstructed=false`, `ready_for_ev=false`, `automatic_clip_selection_authorized=false`.
- Rejects stale hashes, edited audits, cross-table indices, unreviewed fields, card collisions, malformed ranges, duplicate JSON keys, symlinks, and existing output files.

## Synthetic verification

From `video_analyzer/`:

```sh
python -m unittest -v test_offline_omaha_reviewed_equity_bridge test_offline_omaha_equity_mc test_offline_omaha_equity_known_cases
python offline_omaha_reviewed_equity_bridge.py HANDS.json ACTION_AUDIT.json HUMAN_APPROVAL.json NEW_REPORT.json
```

The first command passed **58 selected tests** (22 new bridge tests + 36 Monte Carlo regression tests) locally after publication. Published Python blobs were verified against the exact local Git blob SHA hashes. No GitHub Actions used.

Synthetic demonstration: one PLO5 hand candidate with a human-declared visible 5-card hole observation at 1.0s, a 3-card flop at 2.0s, and a manually supplied one-combination villain range; 100 samples with seed 42 produced a conditional equity estimate of **0.53**. This number is only a reproducible synthetic fixture outcome, not a prediction of a real game.

## Safety boundaries

- The adapter verifies internal JSON consistency and hash linkage, **not independent truth** of video content or human reviewer identity. Even when a recording path is supplied and its hash matches, upstream OCR/crop authenticity must be validated separately.
- A partially reconstructed hand can still support *conditional showdown equity on a selected visible snapshot*; it cannot support an unconditional claim about decision quality or EV.
- The Monte Carlo confidence interval only reflects sampling uncertainty under the explicit opponent range model. It does not cover model/range error.
- No playable tables, live poker integration, opponent bots, EV verdicts, automatic MP4 cuts, or production changes.
- No authorized real video available; OCR accuracy, real hand reconstruction and 40–60 minute performance remain unverified.

## Next

Build a separate, explicitly conditional **single-decision EV** calculator with clear pot/call/raise/fold-equity assumptions, then integrate it only with validated action/pot reviews. Develop MP4 clip export independently using synthetic media and original timestamps; keep automatic selection blocked until video-based evidence quality is measured.
