# Cycle 121 — Offline reviewed-hand comparison

Scope: `docs/VIDEO_ANALYZER_SCOPE.md`. Offline/asynchronous analysis of user-supplied PLO5/PLO6 recordings only. No playable tables, real-time assistance, betting, external integrations, credentials or spending.

## Delivered

- `offline_reviewed_snapshot_page.py` creates a static, local HTML comparison of the **original** human-entered hand draft and the **candidate** produced by accepted independent corrections. Each field shows both versions; accepted changes are highlighted with proposal digest and reviewer reason.
- It reconstructs the Cycle 120 candidate from the original draft, overlay and independent review and requires exact canonical equality with the supplied candidate snapshot. Rejects altered source chains, inconsistent candidate values, duplicate JSON keys, symlinks, overlapping paths, oversized output and overwriting existing files.
- Escapes user-entered labels, cards, notes and reasons; enforces a restrictive CSP, no JavaScript or remote resources; limits the display to 200 hands and 1 MiB HTML.
- **No equity/EV calculation, clip selection or video verification is performed.** Human acceptance is not source-video evidence; all math and clip authorization gates remain false. SHA-256 binds data but does not authenticate reviewer identity.

## Reproduce

From `video_analyzer/`:

```bash
python -m unittest -v test_offline_reviewed_snapshot_page test_offline_hand_reviewed_snapshot test_offline_hand_independent_review test_offline_hand_correction_overlay
python offline_reviewed_snapshot_page.py draft.json overlay.json review.json snapshot.json new_review.html
```

Inputs must be a consistent Cycle 118–120 review chain. Output must not exist. Open the HTML locally in a browser.

## Evidence (2026-10-26)

- 16 new synthetic tests plus 64 prior selected tests: **80/80 passed locally**, including post-publication rerun.
- A Cycle 120 synthetic chain produced a read-only HTML report with 1 hand, 1 accepted correction, 0 rejected, and math authorization false.
- Git blob SHA-1 matched the two locally tested Python files after publication. No remote CI or full-repository suite was run.

## Unverified / blocked

- No annotated authorized real PLO5/PLO6 video. OCR precision, real hand reconstruction, source PTS, equity/EV validity and 40–60 minute throughput are unverified.
- Browser rendering has not been manually inspected on Windows. The EOF clip-duration discrepancy remains unresolved.
- This page is a separate audit view, not yet embedded into the multi-clip session index. It is not a real-time or automated poker decision aid.
