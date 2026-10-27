# Cycle 155 — offline conditional Omaha Monte Carlo

Branch: `feature/plo5-plo6-training`. Scope: `docs/VIDEO_ANALYZER_SCOPE.md`.

## Delivered

- Independent, offline **heads-up high-only** showdown-equity Monte Carlo for PLO5 and PLO6.
- Enforces exactly **two private cards plus three board cards**, rejects duplicate/invalid cards and impossible board lengths.
- Accepts only an **explicit list** of opponent 5-/6-card combinations and a written range assumption; uniformly samples **unblocked** combinations and uniform remaining board runouts.
- Deterministic PRNG seed, sample count, win/tie/loss counts, split-pot equity, conservative conditional 95% Hoeffding interval.
- Strict JSON contract, bounded input/samples/range, rejects duplicate JSON keys, checks source SHA-256, and creates output without overwriting an existing file.
- **Never** asserts that the video/OCR is verified, the hand is complete, the range is factual, EV is calculated, or clips are authorized.

## Local checks

Run from `video_analyzer/`:

```sh
python -m unittest -v test_offline_omaha_equity_mc test_offline_omaha_equity_known_cases
python offline_omaha_equity_mc.py fixtures/offline_omaha_equity_synthetic.json new_equity_report.json
```

The first command was tested locally with 36 passing synthetic tests. The sample scenario was run with 500 trials and seed 42. This is **not** a full repository test, an OCR test, or an actual video test. No GitHub Actions used.

## Boundaries and limitations

- This is **not EV**: it does not model folds, calls, raises, betting, rake, ICM, or future actions.
- The interval captures Monte Carlo sampling uncertainty **conditional on the range**; it does not capture range misspecification or uncertainty about hidden cards/actions.
- One opponent only, no multiway pots or side-pot payouts. All cards/ranges are manual hypothetical inputs, not inferred from video.
- Does not connect directly to upstream OCR/evidence reports; a future gated adapter must verify provenance and completeness before using reviewed hands.
- No real recorded PLO5/PLO6 example was available; video recognition and 40–60 minute performance remain blocked.

## Next

Create a fail-closed bridge from reviewed hand candidates to explicit conditional equity scenarios, requiring evidence hashes, explicit opponent ranges and human approval. Then separately model decision EV and MP4 clipping, without enabling automated conclusions for incomplete hands.
