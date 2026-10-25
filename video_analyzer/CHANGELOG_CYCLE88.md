# Cycle 88 — navigation spans to conservative manual hand-review drafts (2026-10-25)

Scope: `docs/VIDEO_ANALYZER_SCOPE.md`. Offline/asynchronous analysis of user-provided PLO5/PLO6 recordings only. No live poker, playable tables, bots, real-platform integration, credentials, production changes or paid services.

## Implemented

- `boundary_hand_draft.py` consumes the schema-v2 navigation-only output from `boundary_history_bridge.py`, generating one editable, initially unknown hand-review worksheet per candidate span (up to four tables). It retains source task IDs, interior candidate IDs and unresolved-boundary warnings. It never creates a verified hand ID.
- Per-field manual/hypothesis provenance and confidence are explicit for variant, *visible* private cards, *visible* board, observed pot and effective stack. A list of manually entered or hypothetical actions is allowed; timestamps must stay within the source span. Unknown fields remain truly unknown.
- Validation regenerates immutable worksheet metadata from the original navigation JSON and its SHA-256, rejects edited authority flags, duplicate JSON keys, invalid card notation/counts, duplicate visible cards, invalid confidence, invalid timestamps, action ordering and unsupported fields. The output remains blocked for equity, EV, error classification and automatic clip selection, even when a human reports a field.
- Exclusive-create output files and symlink-input rejection prevent accidental overwrites and common path mistakes. File size and entry/action budgets are enforced.
- `test_boundary_hand_draft.py` adds 17 deterministic tests. No poker hand was inferred from OCR.

## Local verification

- 17 new tests passed.
- 112 selected integration/regression tests passed in 21.427s, including FFmpeg on synthetic frames via existing upstream tests. The 112 includes the 17 new tests; suites overlap with earlier cycles.
- No real recorded poker session, full suite, remote CI or hour-long processing was verified.

## Commands

```sh
python video_analyzer/boundary_hand_draft.py template navigation_spans.json editable_hand_draft.json
# Edit only reviewer, reviewer_notes, fields and actions in the generated JSON.
python video_analyzer/boundary_hand_draft.py review navigation_spans.json edited_hand_draft.json reviewed_hand_report.json
```

The original navigation file must be supplied again when validating. Manual labels are not independent video authentication. Neither the template nor the reviewed report is eligible for automatic equity/EV or MP4 ranking.

## Blocker / next

An authorized 3–5 minute PLO5/PLO6 video and independent human annotations are still missing. Next: bind review records to exact visual evidence at each decision timestamp and build a separately validated, hypothesis-explicit mathematical scenario gate.
