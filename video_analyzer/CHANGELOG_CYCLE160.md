# Cycle 160 — Reviewed offline decision to hypothetical EV binding

Scope: `docs/VIDEO_ANALYZER_SCOPE.md`. Only `feature/plo5-plo6-training`; no live poker, playable tables, paid services, production, or credentials.

## Implemented

- `offline_reviewed_decision_ev_link.py`: fail-closed, offline binding of one manually reviewed fold/call/raise to an existing conditional heads-up EV scenario and report. It **recomputes** the source action/street audit and the PLO5/PLO6 Monte Carlo EV calculation, then compares the complete reports.
- Human approval must be bound by SHA-256 to the exact hand candidates, action audit, EV scenario, and EV report. It must identify the hand, table (1–4), decision, and reviewed hero/board/pot/action observation indices. The review must explicitly acknowledge heads-up terminal showdown, pot units, and hypothetical call/raise amounts.
- The visible hero cards and board must match the mathematical scenario; the latest visible pot before the decision must match the scenario pot. A pot snapshot older than five seconds, a newer card/pot observation, an intervening bet/action, a conflicting board, or an ambiguous action timestamp blocks the link.
- Supports PLO5 and PLO6, and hand identity across four synthetic tables. Rechecks optional recording hash and rejects tampering, duplicate JSON keys, symlinks, existing output, invalid indices, and mismatched IDs.
- Output is a **new JSON consistency report**. All action-recommendation, decision-quality and automatic-clip-selection flags remain false. EV ranges and fold probability remain hypotheses; the model still excludes future betting, multiway pots, rake, and verified raise legality.

## Local tests (not GitHub Actions)

Run from `video_analyzer`:

```sh
python -m py_compile offline_reviewed_decision_ev_link.py test_offline_reviewed_decision_ev_link.py
python -m unittest -v test_offline_reviewed_decision_ev_link.py test_offline_four_table_action_timeline_audit.py test_offline_omaha_conditional_ev.py test_offline_omaha_equity_mc.py
```

**131 passed** in the local ChatGPT environment: 38 new synthetic binding tests and 93 existing selected regression tests. PLO5/PLO6, four-table identity, pot/card/action binding, SHA tampering, deterministic EV recalculation, and fail-closed output behavior were exercised. Source blobs published to GitHub were compared against locally tested Git hashes. No complete-repository suite, GitHub Actions, real OCR, or real-session throughput was tested.

## Usage

```sh
python video_analyzer/offline_reviewed_decision_ev_link.py \
  hand_candidates.json action_audit.json ev_scenario.json ev_report.json \
  human_approval.json new_link_report.json --recording optional_recording.mp4
```

Human approval JSON schema version 1 requires these fields (all required):

```json
{
  "schema_version": 1,
  "source_hand_candidates_sha256": "<sha256>",
  "source_action_audit_sha256": "<sha256>",
  "source_ev_scenario_sha256": "<sha256>",
  "source_ev_report_sha256": "<sha256>",
  "reviewer_confirmed_offline": true,
  "hand_id": "hand1", "table_id": 1,
  "decision_id": "example-decision-id",
  "hero_observation_index": 0,
  "board_observation_index": 2,
  "pot_observation_index": 3,
  "action_observation_index": 4,
  "observed_action_label": "call",
  "heads_up_terminal_showdown_is_hypothesis": true,
  "pot_units_reviewed": true,
  "call_cost_and_raise_are_hypotheses": true,
  "reviewer_note": "Reviewed synthetic example only"
}
```

The sample is a **shape illustration**, not a valid approval until its hashes match the actual source files. No card inference, authenticated reviewer identity, verified stack, or automatic clip selection is implied.

## Blockers and next cycle

Still missing an authorized, annotated 3–5 minute PLO5/PLO6 recording to validate OCR, action reconstruction, and timing. Next: safely attach this conditional decision report to an explicitly selected hand clip, and prototype conservative impact prioritization that **does not rank uncertain EV estimates as verified mistakes**. Do not promote hypothetical EV to a decision recommendation.
