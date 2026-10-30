# Cycle 216 — resumable offline math batches and verified session history

Date: 2026-10-30. Branch: `feature/plo5-plo6-training`.

## Implemented
- `offline_session_batch_history.py` consumes the existing **human-reviewed** batch plan and invokes `offline_reviewed_math_runner.run` sequentially with a bounded `--max-new` count (default: 1).
- The history records hand IDs, table IDs, original timestamps, calculated or blocked status, declared reviewer confidence, Monte Carlo seed/iterations, conditional equity, sampling-only CI and optional terminal-call EV.
- Existing batches are verified against the original reviewed plan, annotations and queues before resume. Completed result batches must form a prefix; no output batch is overwritten.
- The history is updated with an atomic rename. A valid, stale prefix history is accepted after interruption between result publication and history publication; other modifications are rejected.
- `--verify` checks the full history and result files without rerunning Monte Carlo.
- Retains explicit flags: OCR unverified, cards unverified independently, opponent ranges hypothetical, CI only sampling uncertainty, no action grading and no live assistance.

## Locally verified
- 14 new synthetic unit tests (205 hands over four tables, three batches, one eligible Monte Carlo hand with 120 iterations, 204 blocked).
- 130 selected tests passed including regression suites for planner, equity runner, review queue, math clip gallery, timeline and clip gallery.
- Verified Git blob SHA parity for the published module and tests against locally tested bytes.
- No GitHub Actions used.

## Limitations
- No authorized annotated video was supplied. No real OCR, real hand reconstruction, Windows/browser playback, full 40–60-minute recording, or complete repository suite was validated.
- A result hash proves local consistency, not correctness of manually declared cards, opponent ranges, or strategy.
- This component creates structured cross-batch history, **not** a unified HTML timeline or MP4 export. Those remain future integration work.
- No changes to `main`, production, credentials, or paid services.

## CLI
```bash
python offline_session_batch_history.py plan.json annotations.json batches results --max-new 1
python offline_session_batch_history.py --verify plan.json annotations.json batches results
```
The `batches` directory must first be generated and verified by `offline_session_batch_planner.py`.
