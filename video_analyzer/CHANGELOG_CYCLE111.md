# Cycle 111 — Manual MP4 clip ↔ hypothetical PLO math provenance (2026-10-26)

**Branch:** `feature/plo5-plo6-training` only. **Scope:** `docs/VIDEO_ANALYZER_SCOPE.md` — offline, user-uploaded recorded sessions; no playable tables, live poker integration, betting automation, production, credentials or paid services.

## Implemented

- `offline_clip_math_provenance.py` adds a **read-only, source-bound linkage** between the Cycle 109 manual MP4 clip and its sidecar, the Cycle 110 bounded FFprobe frame-PTS audit, Cycle 107 human-entered hand draft, and Cycle 108 blank/filled math worksheet and hypothetical math result.
- Requires the **original recording**, exported MP4 and six JSON files; recomputes SHA-256 of the actual media, checks source identity, table (1–4), human-assigned hand ID, decision timestamp inside the clip, human-claimed hand interval overlap, geometry/duration, PTS audit identity and consistency, protected worksheet metadata, source hand entry digest, Monte Carlo trial/seed/outcome counts, and explicit model/sampling limitations.
- Validates human-reviewed decision cards, board, pot/call and action against the hand draft, and math parameters against the filled worksheet. Prevents cross-table/cross-hand misassociation, duplicate JSON keys, symlinked JSON/media, non-finite numbers, and output overwrites. Uses exclusive creation and rechecks all input digests before writing.
- Outputs a **new JSON provenance manifest**. It does **not** change the original MP4 or its human subtitle, calculate/recalculate equity, infer hidden cards, validate actual hand boundaries, prove an error, or select clips automatically. All verification/automatic-action flags remain false.
- The math result is **not independently recomputed** by this adapter. It binds to the supplied math result and its hashes, and preserves the explicit distinction between sampling CI and uncertainty in ranges, OCR, or models.

## Local verification

- `python -m unittest -v test_offline_clip_math_provenance`: **20 tests passed**, including PLO5/PLO6, four manual table IDs, real synthetic FFmpeg MP4/FFprobe, hash tampering, source/hand/table mismatch, incorrect action timestamps, forged math gates, inconsistent Monte Carlo parameters, duplicate JSON keys, symlinks, and no-overwrite.
- `python -m unittest -v test_offline_clip_math_provenance test_offline_clip_frame_pts_audit test_offline_manual_clip_export`: **43 selected tests passed** (20 new + 17 frame audit + 6 clip export).
- `python -m py_compile offline_clip_math_provenance.py test_offline_clip_math_provenance.py`: passed.
- Synthetic demonstration: generated 12-second 160×120 test pattern, selected a human-described 2-second MP4 clip, audited source frame PTS, and linked it to the **previously computed synthetic PLO5** Monte Carlo result from Cycle 108 using a new source-bound worksheet/draft identity. No real poker footage; no new Monte Carlo run in this cycle.
- The four existing dependency files used locally were verified against their Git blob SHAs on the authorized branch before the tests: `offline_manual_clip_export.py`, `offline_clip_frame_pts_audit.py`, `offline_job_hand_history_draft.py`, and `offline_job_hand_math_review.py`. This is a **selected regression**, not a full branch checkout.

## Not verified / blocked

- Full exact-branch test suite, remote CI, real PLO5/PLO6 footage, OCR precision, authentic hand/action PTS, Monte Carlo recomputation by this adapter, and complete 40–60-minute video-to-explanatory-MP4 workflow.
- No authorized annotated 3–5-minute recording was provided. Continue with synthetic components and retain this calibration blocker.

## Next

1. Test export frame alignment: compare decoded frames near requested source PTS with decoded frames at the exported MP4 edges, including VFR and nonzero-origin sources. Treat differences as measurements, not proof of poker hand boundaries.
2. Add an offline review/report screen displaying the linked MP4, hypothetical math CI/assumptions, and human correction workflow without presenting a strategic verdict.
3. Calibrate OCR and hand segmentation against a consented annotated PLO5/PLO6 video; measure field-level precision and uncertainty.

### CLI

```bash
python video_analyzer/offline_clip_math_provenance.py \
  recording.mp4 manual_clip.mp4 manual_clip.json frame_pts_audit.json \
  hand_drafts.json blank_math_worksheet.json filled_math_worksheet.json \
  hypothetical_math_results.json --table 1 --hand H1 --output linked_provenance.json
```

All inputs are local files; the output path must not already exist.
