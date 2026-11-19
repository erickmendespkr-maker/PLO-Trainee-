# Offline visual evidence adaptation — Baivaras/poker-data-scraper

Reference: https://github.com/Baivaras/poker-data-scraper

## Scope and provenance
This is an independent design adaptation for **recorded MP4 PLO5/PLO6 only**. No live capture, PokerStars integration, model weights, source-code copying, or runtime dependency is introduced. External repository licensing must be established before any code reuse.

## Evidence pipeline
1. Use FFmpeg-decoded media PTS and per-table ROI calibration, not wall-clock timestamps.
2. Per-table card, board, pot, stack, bet, action-label regions; store crop hashes and OCR raw values with confidence.
3. Compare successive frames, requiring repeated stable stack decreases before recording candidate committed BB. Never treat a decrease alone as a loss.
4. Prefer explicit hero FOLD text near avatar; disappearance of cards is weak corroborating evidence, not definitive fold.
5. Maintain per-hand accumulated contributions separately from visible stack and pot; flag OCR gaps, rebuys, and stack increases as uncertain.
6. Once fold is verified, contribution becomes a *candidate realized hand loss*; retain video clip until next verified deal, not fold timestamp.
7. Start next hand only on verified new private cards/new deal, per table; board transitions and pot resets alone are not sufficient.
8. Require human review of high-impact losses until recognition precision is measured on annotated real recordings.
9. For equity/EV use only independently implemented PLO5/PLO6 rules, explicit ranges, Monte Carlo seed and uncertainty. No GTO claim.

## Synthetic prototype (not yet integrated)
An independent stdlib-only prototype `offline_fold_loss_evidence.py` and `test_offline_fold_loss_evidence.py` were created and exercised locally in a separate workspace (8/8 unit tests). These artifacts have **not** been committed as source in this repository and do not establish real-video accuracy.

## Known limits
- Stable stack delta can include non-bet effects, skipped frames and OCR errors; investment cannot be proven from stack alone.
- If fold happens before investment has been observed, the computed contribution is a lower bound, not a reliable total.
- Explicit FOLD label must be matched to the hero's table ROI and confirmed against neighboring frames.
- The external classifier is trained on two-card PokerStars crops, not five/six-card PLO video; do not import its model.
- The actual video and ground-truth annotated hands were not available for validation in this cycle.

## Next acceptance test
On an authorized recorded sample: annotate 5–10 hands across tables, including fold after >30 BB, no-fold stack changes, rebuy, OCR dropout, and same-card-looking subsequent deals. Measure event-level precision/recall, compare loss BB to manual ledger, and verify FFmpeg MP4 clip boundaries. Do not promote unverified events to definitive decisions.
