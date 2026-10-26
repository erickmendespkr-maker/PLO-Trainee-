# Cycle 122 — Offline session-to-reviewed-hand crosswalk

Scope: `docs/VIDEO_ANALYZER_SCOPE.md`. Offline/asynchronous, user-supplied PLO5/PLO6 recordings only. No playable tables, live assistance, betting, external poker integration, credentials, or spending.

## Delivered

- `offline_reviewed_session_crosswalk.py`: creates a **single local, static HTML view** joining up to 40 manually selected MP4 clips with the **original and candidate reviewed hand fields** from the Cycle 118–121 independent-review chain.
- Requires an exact match of `job_id`, source-recording SHA-256, `table_id`, and human-assigned hand label. Validates the full reviewed snapshot chain by rebuilding it from draft/overlay/review, validates each clip link against the MP4 SHA-256, and validates optional sampled visual reports. Rejects mismatched PLO variants and duplicate hand identities.
- Clearly lists clips with no reviewed hand and reviewed hands with no clip. Warns when the manually reviewed PTS interval disagrees with the clip's claimed decision timestamp or does not overlap the selected clip window.
- Presents old hypothetical equity/EV as **previously calculated under their original assumptions**. Never recalculates math from reviewed cards, declares an error, promotes human agreement to video evidence, or authorizes automatic clip selection.
- Protects against unsafe paths, symlinks, repeated files, duplicate JSON keys, NaN, tampered source chains, modified MP4 files, HTML injection, output overwrite and input modification during generation. Output has restrictive CSP and no JavaScript or remote resources.

## Reproduce

From `video_analyzer/`:

```bash
python -m unittest -v test_offline_clip_review_page test_offline_session_review_index test_offline_hand_correction_overlay test_offline_hand_independent_review test_offline_hand_reviewed_snapshot test_offline_reviewed_snapshot_page test_offline_reviewed_session_crosswalk
python offline_reviewed_session_crosswalk.py session.json draft.json overlay.json review.json snapshot.json new_crosswalk.html
```

All inputs and the new HTML output must be in the same local directory; the output file must not exist. The session's link manifests must use the same job/source digest as the hand-history draft.

## Evidence (2026-10-26)

- **22 new tests** passed with a synthetic FFmpeg-generated MP4 and a genuine Cycle 118–120 synthetic review chain.
- **155/155 selected tests** passed locally across seven suites (including the new tests). Full-repository suite and remote CI were **not** run.
- A four-table synthetic demo produced a local HTML view: 4 clips, 1 exact manual association, 3 clips without reviewed hands; all math and automatic-selection gates remain false.
- After publication, verify remote Git blob content and rerun the same local suite; do not claim post-publication checks unless executed.

## Unverified / blocked

- No authorized annotated real PLO5/PLO6 video; real OCR accuracy, hand reconstruction, video-to-hand alignment, decoded-frame PTS, and 40–60-minute performance remain unverified.
- Matching IDs and SHA-256 values provide a consistency crosswalk, not proof that the video depicts the claimed cards/actions.
- Browser rendering on Windows and the prior EOF clip-duration edge case remain unverified/unresolved.
- The HTML is an offline report, not a processing/upload GUI or a complete end-to-end analyzer.
