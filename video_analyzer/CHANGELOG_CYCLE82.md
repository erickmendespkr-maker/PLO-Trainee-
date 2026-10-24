# Cycle 82 — conservative OCR hand-transition review windows

Scope: offline/asynchronous analysis of recorded PLO5/PLO6 sessions only, following \`docs/VIDEO_ANALYZER_SCOPE.md\`. No playable tables, opponents, live poker integration, or betting automation.

## Implemented

- Added \`activity_ocr_boundary_triage.py\`: consumes the Cycle 81 \`unverified_temporal_ocr_review_hints\` JSON and produces candidate **review windows**, not reconstructed or confirmed hand boundaries.
- Isolates up to four tables; recognizes changes in *candidate* visible private cards and non-extension board changes. Normal flop-to-turn-to-river board extension is not a hand transition.
- Pot decreases are **context only** and cannot create a hand-transition candidate by themselves. A matching exact window can raise review priority. Windows are not fuzzily merged.
- Duplicate same-field changes or uncertain OCR/timing observations inside a window prevent elevated priority. All outputs explicitly forbid automatic equity, EV, strategic-error claims and clip selection.
- Validates schema, statuses, candidate cards/amounts, timestamp windows, source evidence SHA-256 references, report counts, and bounded input size. Refuses symlink input and overwriting outputs; uses atomic hard-link creation for JSON.

## CLI

\`\`\`sh
python video_analyzer/activity_ocr_boundary_triage.py temporal_review.json --output boundary_review.json
\`\`\`

## Tests actually executed (synthetic)

- 16 new unit tests: passed.
- 51 selected tests (new module + Cycle 81 OCR temporal, crop OCR, PTS audit and table stills): passed.
- Integration demonstration from Cycle 81 synthetic OCR report: 4 tables, one 1–2s review window, \`review_first\` only because exact-window private-card change and pot drop; no hand verified.
- Earlier Cycle 81 pot-only synthetic report produced zero boundary candidates (expected).
- Python compilation: passed.
- Full \`unittest discover\` attempt exceeded 200 seconds and did **not** complete; full suite is **not verified**. No remote CI claimed.

## Blockers and next steps

No authorized real 3–5 minute PLO5/PLO6 recording or human-labeled ground truth. Recognition precision, real hand segmentation and full 40–60 minute session throughput remain unverified. Next: reviewer confirmation of candidate windows with frame evidence, then benchmark against human annotations. Do not authorize equity/EV or automatic MP4 selection until the hand history is sufficiently reviewed.
