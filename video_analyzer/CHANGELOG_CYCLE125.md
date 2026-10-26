# Cycle 125 — offline per-street contribution ledger

Scope: `docs/VIDEO_ANALYZER_SCOPE.md`. Only recorded PLO5/PLO6 analysis; no real-time play, bots or betting integrations.

## Delivered

- `offline_street_contribution_ledger.py`: deterministic, input-only event ledger for 1–4 table IDs, one hand per input, integer incremental chips, preflop blind posts, per-street contribution reset, player stacks, pot conservation, chronological PTS and observation confidence.
- Calls `offline_pot_limit_decision_bounds.assess` with explicit actor street contribution, highest street contribution, pot before event and stack before event. Missing full-raise increment remains unknown rather than inferred.
- Warning flags and false verification gates. Report SHA-256 is a canonical input digest, not proof of video provenance.
- JSON CLI with duplicate-key rejection, bounded input and exclusive output creation.

## Test evidence

- 29 new synthetic unit tests.
- 84 selected tests passed locally when combined with prior pot-limit bounds and betting-action triage suites (55 existing tests). This is not the repository-wide test suite.
- No real video, OCR, equity, EV or MP4 export was validated this cycle.

## Limitations

- Blind/ante assumptions, missed actions, uncalled bet returns, multiway side pots and action reopening are not reconstructed. Starting pot and full-raise increments must be explicitly supplied.
- The synthetic fixture is not evidence of video accuracy. Betting rules and readiness for equity/EV remain false.
- A 3–5 minute authorized annotated PLO5/PLO6 recording is still missing.

## Next

- Add evidence linkage from table/hand event rows to frame crops and source recording SHA-256; keep confidence and PTS uncertainty visible.
- Investigate end-of-recording MP4 frame timing with FFprobe; do not synthesize missing frames.
