# Cycle 211 — fail-closed human-reviewed hand to math input queue

## Scope
Adds `offline_reviewed_hand_math_queue.py` to bridge the existing `offline_manual_roi_review.review_plan` JSON with explicit human card annotations and prepare input records compatible with `offline_plo_equity_monte_carlo.analyze`. The bridge does **not** run Monte Carlo, infer cards, determine hero identity, grade actions, or connect to poker services.

## Usage
From `video_analyzer/`:

```bash
python offline_reviewed_hand_math_queue.py REVIEW_PLAN.json MANUAL_CARDS.json NEW_QUEUE.json
```

Manual card annotation schema:

```json
{
  "schema_version": 1,
  "source_plan_sha256": "<sha256 of REVIEW_PLAN.json>",
  "hands": [{
    "hand_id": "H001", "table_id": "T1", "variant": "PLO5",
    "card_review_status": "human_confirmed",
    "hero_cards": ["As", "Kd", "Qh", "Jc", "Tc"],
    "board_cards": ["2c", "3d", "4h"],
    "card_evidence": [{"card": "As", "pts_seconds": 12.5, "source": "human_frame_review"}],
    "opponent_model": {"kind": "uniform"},
    "iterations": 1000, "seed": 42,
    "reviewer_confidence_declared": 0.8
  }]
}
```

**Important:** `card_evidence` must contain one entry for *every* declared hero and board card, not just the one shown in this abbreviated illustration. Frame timestamps and confidence are reviewer claims, not independently checked against decoded frames.

Each hand receives a deterministic eligible/blocked entry. Only eligible hands contain `equity_input` and `manual_review_confirmed=true`. Missing annotations, incomplete cards, unconfirmed OCR, missing frame evidence, missing ranges or simulation parameters, and fully blocked weighted ranges cannot enter the math queue. Weighted combos are checked for card blockers and duplicates. No automatic strategy grading.

## Evidence
- 18 synthetic Python unit tests passed locally, including duplicate JSON keys, invalid PTS, cross-table IDs, blocked ranges, PLO6 and CLI non-overwrite.
- Tests do not establish Monte Carlo accuracy or video/OCR accuracy.
- No real recorded PLO5/PLO6 sample was available.

## Next
Consume eligible queue records with the existing Monte Carlo engine, preserve per-hand result hashes and attach them to reviewed clips only after independent binding checks. Validate against an authorized annotated 3–5 minute recording when available.
