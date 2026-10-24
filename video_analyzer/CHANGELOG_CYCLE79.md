# Cycle 79 — audited decoded FFmpeg PTS for math-review navigation stills

Scope: offline PLO5/PLO6 recorded-session video analysis only; no live play or betting.

## Implementation
- `activity_math_review_pts_audit.py` verifies the source video and all review-chain JSON against the independently recomputed frame plan.
- For each previously exported navigation PNG, FFmpeg re-decodes the requested seek using `-copyts` and `showinfo` to observe filtergraph PTS ticks and time base.
- A decoded PTS is reported **only** when the re-decoded PNG is byte-identical to the upstream SHA-256-verified PNG. Otherwise the PTS stays null and the mismatch is explicit.
- Rejects tampered manifests/stills, symlinks, ambiguous PTS, non-finite values, pre-existing output directories, and changes to sources during processing. Publishes an atomic JSON report.
- No hand, card, OCR, equity, EV, clip-selection, or strategic-error authorization is granted.

## Verification
- New synthetic tests: 7 passed (`python -m unittest -v test_activity_math_review_pts_audit`).
- Focused integration/regression: 47 passed (`python -m unittest -v test_activity_math_review_pts_audit test_activity_math_review_frames test_activity_math_review_table_stills test_activity_math_review_handoff test_activity_math_readiness_triage test_source_pts_evidence`).
- Full suite was attempted but exceeded execution time; no full-suite pass is claimed.
- No real PLO5/PLO6 video provided; no real-world OCR/recognition accuracy claim.

## Example
```sh
python video_analyzer/activity_math_review_pts_audit.py \
  recording.mp4 frames_dir handoff.json triage.json packet.json timeline.json pts_audit_dir
```

Result: `pts_audit_dir/math_review_pts_audit.json`.

Note: `decoded_frame_pts_seconds` is FFmpeg **filtergraph** PTS, not capture wall-clock time, and is only reported for byte-identical re-decodes. Nonzero stream start offsets must be considered before cross-pipeline time alignment.
