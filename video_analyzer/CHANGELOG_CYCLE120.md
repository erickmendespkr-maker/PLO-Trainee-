# Cycle 120 — Immutable reviewed hand candidate snapshots

Scope: `docs/VIDEO_ANALYZER_SCOPE.md`. Offline/asynchronous PLO5/PLO6 recorded-video review only. No live assistance, poker gameplay, AI opponents, platform integration, credentials, production or spending.

## Added

- `offline_hand_reviewed_snapshot.py`: builds a **new** candidate hand-history JSON by applying **only** accepted corrections from the Cycle 118 overlay and Cycle 119 independent-review report. Rejected corrections are listed separately and never applied. The original draft, overlay and review files remain unchanged.
- Recomputes the Cycle 119 review from source inputs, checks its canonical representation, and binds the candidate to SHA-256 digests of the draft, overlay, review, original hand entries, accepted proposals and derived values. This detects inconsistent provenance; **SHA-256 does not authenticate a human reviewer**. Review reasons and reviewer labels are self-declared and can be changed if the review file itself is replaced without an independently trusted digest.
- Revalidates the merged candidate's visible-card uniqueness, PLO5/PLO6 card count, hand interval, action chronology, board street presence, action amount semantics and call-vs-stack bound. These are structural checks, not complete poker betting rules or proof of video accuracy.
- Supports legacy Cycle 119 synthetic drafts without attestation fields; does **not** infer missing attestations. A partially present attestation pair is rejected.
- Refuses unsafe/oversized/duplicate-key input JSON, symlinks, overlapping paths and overwriting existing output; writes a separate JSON file with exclusive creation.
- **All math, video and clip authorization gates stay false** in the new candidate snapshot, even when every correction is accepted.

## Reproduce locally

From `video_analyzer/`:

```bash
python -m unittest -v test_offline_hand_reviewed_snapshot test_offline_hand_independent_review test_offline_hand_correction_overlay
python offline_hand_reviewed_snapshot.py draft.json overlay.json independent_review.json new_snapshot.json
```

A synthetic example can be constructed from the Cycle 119 demonstration draft, overlay and review report. The CLI creates a new candidate snapshot; it does not modify any of its inputs.

## Test evidence (2026-10-26)

- **25 new synthetic tests** for candidate application, provenance, rejection, tampering of derived fields, input validation, PLO6, four tables, deterministic output, and safe writes.
- **39 existing selected tests** for correction overlay and independent review.
- **64 selected tests passed locally**. Published source and tests matched the locally executed files by Git blob SHA-1; rerun after publication. This is **not** a full repository suite or remote CI verification.
- One synthetic Cycle 119 input chain generated a candidate snapshot with 1 accepted correction, 0 rejected, 0 math-ready hands.

## Unverified / blocked

- No authorized annotated real PLO5/PLO6 recording: OCR accuracy, hand reconstruction, source PTS, video provenance and 40–60 minute performance are **not verified**.
- Snapshot acceptance does **not** authorize Monte Carlo equity, EV, automatic hand selection or clip generation. Complete betting-rule verification and source-video attestation remain separate work.
- Review labels are not authenticated; the tool cannot independently prove the identity or integrity of a substituted but internally consistent review file.
- EOF clip-duration discrepancy from earlier cycles remains unresolved.
