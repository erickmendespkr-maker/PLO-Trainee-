# Cycle 110 — Bounded frame PTS audit for human-selected clips (2026-10-25)

Branch: `feature/plo5-plo6-training`. Scope: `docs/VIDEO_ANALYZER_SCOPE.md`. Offline user-supplied recordings only; no live poker, betting integration, bots, credentials, production or paid APIs.

## Implementation
- New `offline_clip_frame_pts_audit.py` reads the existing Cycle 109 manual selection JSON and SHA-256-checks the original recording before and after frame sampling.
- FFprobe samples decoded video-frame `best_effort_timestamp_time` near **both manually selected edges**; reports nearest *observed* frame PTS, signed offset, tolerance, frame counts, local gap distribution and whether variable spacing was observed in the local sample.
- Rejects ambiguous or nonzero video PTS origins (>0.05s), unsupported durations, invalid selections/crops, changed source, unsafe input/output paths, missing frames and malformed frame timestamps. Creates a new JSON audit without overwriting.
- Explicitly records that `-read_intervals` uses approximate seeks and that nearest *observed* PTS is not guaranteed globally nearest. Frame proximity does not prove hand boundaries or action timestamps, nor that FFmpeg trims are frame-exact. Local gap variation does not classify the entire recording as VFR.
- No promotion of OCR, human claims, equity/EV or strategic error verdicts. All automatic clip selection gates remain false.

## Local verification
- `python -m unittest -v test_offline_clip_frame_pts_audit test_offline_manual_clip_export`: **23 passed** (17 new, 6 previous), with synthetic CFR, variable frame spacing, sparse frames, nonzero-origin PTS rejection, SHA mismatch, 4 table IDs, symlink/duplicate-key/overwrite checks and real FFmpeg MP4 export with subtitles.
- `python -m py_compile offline_clip_frame_pts_audit.py test_offline_clip_frame_pts_audit.py`: passed.
- Synthetic demonstration includes a 4-second source, human-selection JSON, frame-audit JSON and a 2-second MP4 clip with human subtitle. The demonstration is **not** real poker footage.

## Not verified
- Full exact-branch test suite, remote CI, real PLO5/PLO6 footage, actual hand boundaries, end-to-end OCR/equity/EV-to-clips, source PTS normalization for nonzero origins, full one-hour real-world processing.

## Next
- Normalize and explicitly test source PTS origins and variable-frame-rate offsets; compare decoded frames at trim edges against exported MP4.
- Bind clip sidecars to hand-history IDs and hypothetical math review results with source hashes while preserving all non-verification gates.
- Calibrate OCR and true hand boundaries against authorized annotated 3–5-minute footage.