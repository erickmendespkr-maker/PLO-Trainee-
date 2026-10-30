# Cycle 212 — verified reviewed-hand queue -> offline Monte Carlo -> verifiable results

## Scope
Adds `offline_reviewed_math_runner.py` and `test_offline_reviewed_math_runner.py`. This is an **offline** batch bridge from a reviewed clip plan, manual card annotations and the queue from Cycle 211 to the existing `offline_plo_equity_monte_carlo.analyze` engine. No live poker connection, playable tables, opponent agents, automatic card detection or action grading.

## Usage
Run in `video_analyzer/` with Python 3.10+:

```bash
python offline_reviewed_hand_math_queue.py REVIEW_PLAN.json MANUAL_CARDS.json NEW_QUEUE.json
python offline_reviewed_math_runner.py REVIEW_PLAN.json MANUAL_CARDS.json NEW_QUEUE.json NEW_RESULTS_DIRECTORY
python offline_reviewed_math_runner.py --verify REVIEW_PLAN.json MANUAL_CARDS.json NEW_QUEUE.json NEW_RESULTS_DIRECTORY
```

The runner recomputes the **entire** queue from the two source JSON files, checks SHA-256 of all three inputs, rejects modifications, and processes eligible hands only. It preserves blocked hands as blocked records. A staging directory is published only after successful computation and source rechecks. It never overwrites an existing results directory. The batch limit is 20 eligible hands and 200,000 total iterations to prevent unbounded runs.

`NEW_RESULTS_DIRECTORY/manifest.json` contains the video hash **claim**, source SHA-256 hashes, per-hand timestamps, table ID, status, per-hand output SHA-256, original reviewer confidence **not calibrated**, simulation seed, iteration count, equity, **sampling-only** 95% interval and an optional terminal-showdown call EV model. `hands/H001.json` and similar files are produced only for eligible hands.

The `--verify` command rebinds source files to the queue, verifies manifest and result hashes, identities, simulation count invariants and rejects unlisted files and symlinks. It does **not** independently rerun simulations or establish mathematical validity of the Monte Carlo engine.

## Mathematical limitations
- Equity uses **exactly two** private cards and **three** board cards per five-card hand, for one opponent with a declared uniform or weighted-combo range.
- Confidence intervals describe sampling uncertainty only. They do not cover OCR errors, human annotation errors, inaccurate opponent ranges, player identification, or future betting.
- Terminal call EV is an explicitly simplified heads-up showdown model, not an observed action grade. Raise EV is not computed.
- A source video SHA-256 value and per-card frame timestamps are reviewer claims from earlier steps, not independently validated by this module.

## Local evidence
- 18 new synthetic runner tests plus 18 existing queue regression tests passed locally.
- Demonstration exercised real Monte Carlo execution with 120 iterations and one blocked hand, checked output hashes, and reran the independent verifier.
- Additional four-table/PLO6 and known-win conditional EV cases passed in synthetic tests.
- No real recorded video was supplied; no real OCR accuracy or Windows/60-minute performance was measured.

## Next
Bind the per-hand manifest to the offline clip gallery, and validate recognition accuracy against an authorized annotated 3–5 minute PLO5/PLO6 video when available.
