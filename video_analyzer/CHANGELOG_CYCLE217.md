# Cycle 217 — verified multi-batch offline timeline with optional MP4 links

Date: 2026-10-30. Branch: `feature/plo5-plo6-training`.

## Implemented
- New `offline_session_batch_timeline.py` consumes the already verified, resumable `session_history.json` and renders a read-only `WORKSPACE/batch_timeline.html` for up to four tables and 4,000 human-declared hands.
- Math results are linked to their existing per-batch JSON records; conditional equity, sampling-only confidence interval, seed, iterations and optional terminal-call EV are shown alongside explicit uncertainty.
- Optional `WORKSPACE/clips/batch-NNNN/` directories can add previously exported reviewed MP4 clips. Each directory is validated by `offline_reviewed_clip_gallery.build`, the clip manifest is bound to its batch plan SHA-256, and every linked hand must match the verified history's ID, table and timestamps.
- Missing MP4 clips are displayed as missing, never invented. Partial completed-batch prefixes are labeled partial.
- Rejects tampered math/history/video hashes, unbound clip manifests, mismatched table IDs, symlinks, unexpected clip directories and existing output files. `--verify` regenerates the expected HTML and checks exact bytes.
- HTML escapes all human explanations and uses a restrictive Content Security Policy. This is an offline **reviewer-declared** timeline, not OCR validation or a poker action grader.

## Locally verified
- 13 new tests passed, including a real FFmpeg-generated **synthetic 4-second MP4** and cross-batch 102-hand/four-table fixture.
- 105 selected tests passed including existing history, planner, math runner, clip gallery and timeline regressions. No GitHub Actions were run.
- A separate HTML-only rendering stress test produced 4,000 synthetic blocked records (this is **not** a full 4,000-video processing benchmark).
- The demonstration's 102 reviewed records have two completed math batches, one conditional Monte Carlo result (120 iterations), 101 blocked records and one synthetic MP4 link.
- The Git blob SHA-1 of the module and test file matched the locally tested source.

## CLI
```bash
python offline_session_batch_timeline.py plan.json annotations.json batches workspace
python offline_session_batch_timeline.py --verify plan.json annotations.json batches workspace
```
Prerequisite: `workspace/results/` must already be created and verified by `offline_session_batch_history.py`. Optional clips use `workspace/clips/batch-NNNN/`. The HTML is created at `workspace/batch_timeline.html` and never overwrites existing files.

## Not verified
- No authorized annotated PLO5/PLO6 recording has been provided. OCR accuracy, automatic reconstruction of hands/actions, Windows MP4 playback, and full 40–60-minute real sessions remain untested.
- The synthetic MP4 is a generated color test clip, not a poker hand. The gallery verifies bytes and declared binding, **not** independent visual authenticity or video-duration correctness for arbitrary user clips.
- No complete repository-wide test suite was run. No changes to `main`, production, credentials, live poker integration or paid services.
