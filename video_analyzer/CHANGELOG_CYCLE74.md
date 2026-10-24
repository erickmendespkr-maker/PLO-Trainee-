# Cycle 74 — Offline hand-review packets

Scope: `docs/VIDEO_ANALYZER_SCOPE.md`. Only recorded PLO5/PLO6 video, offline/asynchronous. No playable tables, live integration or automated poker verdicts.

## Added

- `activity_hand_review_packet.py`: consolidates reviewed hand timelines, consistency flags, ROI frame suggestions and optional OCR comparisons into **one bounded, per-hand JSON packet** for manual review.
- Uses existing audit, visual crosswalk and OCR-timeline validators rather than guessing hand identities, clock synchronization or poker actions.
- OCR candidates attach to a hand only when there is exactly one matching *human-reviewed field at the exact declared PTS* and a reviewer-declared OCR clock alignment. Ambiguous, unaligned and unmatched candidates remain in a separate unassigned queue.
- ROI frame suggestions require the independent reviewer-declared queue alignment and are restricted to the matching hand, table, field and interval.
- Counts retain omitted OCR candidates when per-hand or unassigned output budgets are reached. Source hashes and explicit non-authority flags remain in the output.
- Does not copy unverified OCR parsed values into the reconstructed hand or authorize equity, EV, automatic clip selection or strategic error labels.
- `test_activity_hand_review_packet.py`: synthetic coverage for four tables, no alignment, explicit alignments, OCR disagreement, ambiguous hand joins, budgets, determinism, SHA mismatch, unsafe inputs and CLI/no-overwrite.

## Usage

```bash
python activity_hand_review_packet.py queue.json timeline.json packet.json \
  --queue-alignment-json queue_alignment.json \
  --ocr-json ocr_candidates.json --ocr-alignment-json ocr_alignment.json
```

Both alignments are **optional**; without them, the packet is still generated, but unverified evidence is not assigned by guesswork. The command never reads a live poker client and never produces betting instructions. JSON source files must be regular files; output must be a new file.

## Limitations

The inputs are precomputed artifacts from upstream modules. No original video frames are decoded or reaudited by this assembler. OCR confidence is engine-reported and uncalibrated; human IDs and clock declarations are not independently verified. No authorized real sample has been supplied; recognition accuracy, automatic hand reconstruction and 40–60 minute throughput remain unverified.
