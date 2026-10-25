# Cycle 107 — human-entered structured hand-history drafts (2026-10-25)

## Scope and safety
Only `feature/plo5-plo6-training`. Offline/async analysis of user-supplied PLO5/PLO6 session recordings. No playable tables, live assistance, real-poker integration, credentials, or paid services.

## New component
- `video_analyzer/offline_job_hand_history_draft.py` consumes the Cycle 106 *unverified* manual reconstruction checklist and a separate JSON human submission, producing a structured, explicitly **unverified** hand-history draft.
- Enforces 5 or 6 hero cards by variant, card notation/uniqueness across visible cards, flop/turn/river order, actor/action/street vocabulary, nonnegative chip amounts, monotonic action order and claimed PTS, at most four tables, and source identity via canonical checklist SHA-256.
- Preserves the original checklist's nominal intervals and source-image hashes; stores manual entries and human confidence separately from video facts.
- Supports incomplete hands without filling missing values. Human PTS checks and attestations are self-reported, **not independently verified**.
- Rejects unknown input fields, duplicate JSON keys, NaN/Infinity, input symlinks, input mutation during processing, and output overwrites. Bounds file sizes and action/hand counts.
- All `ready_for_equity_or_ev`, `hand_reconstruction_verified`, and `automatic_clip_selection_authorized` flags remain **false** even for structurally complete drafts. No mathematical calculation or clip selection is performed.

## Synthetic verification
- 32 unit tests passed, covering PLO5/PLO6, four-table separation, missing fields, duplicate cards, invalid actions, source hashes, timestamps, tampering, symlinks, and exclusive output creation.
- CLI smoke test used a synthetic Cycle 106 checklist and one synthetic hand; generated a JSON draft and checked that `math_ready` stayed zero.
- These checks are local and **not** a full exact-branch regression. No real recording, source-PTS verification, OCR accuracy, or full 40–60 minute video processing was tested.

## Next
Independently verify source video PTS, evidence and action sequence; bind independently reviewed histories to hypothetical equity/EV scenarios without promoting OCR assumptions to facts. Obtain an authorized annotated 3–5 minute PLO5/PLO6 sample to measure visual reconstruction accuracy.
