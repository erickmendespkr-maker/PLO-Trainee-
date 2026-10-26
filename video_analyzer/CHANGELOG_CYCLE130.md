# Cycle 130 — conservative terminal-sequence audit

Scope: `docs/VIDEO_ANALYZER_SCOPE.md`. Offline/asynchronous PLO5/PLO6 video review only; no playable tables, live poker integration, credentials or paid services.

## Added

- `offline_ffmpeg_clip_tail_sequence_audit.py`: bounded 2-second FFmpeg decoded-frame tails at 160×90 grayscale. Compares terminal frame and preceding frames, reporting **possible** added terminal duplicates and **possible** missing terminal frames; static source content is explicitly indeterminate. Includes before/after SHA-256 checks, no-overwrite CLI, and conservative failure on malformed/excessive decoded output.
- `test_offline_ffmpeg_clip_tail_sequence_audit.py`: pure synthetic frame tests plus actual FFmpeg synthetic MP4s for normal, shortened, padded/duplicated, static, remuxed, and VFR cases; unsafe input/output tests.

## Local verification

- 22 new tests passed on Python 3.13.5 and FFmpeg 7.1.5. The tests are **not** a full-repository regression suite.
- Synthetic examples exercise last-frame omission and FFmpeg `tpad=stop_mode=clone` duplication.
- No authorized PLO5/PLO6 session video available; no OCR/hand accuracy, equity/EV, or 40–60-minute performance verified.

## Limits

- Pixel thresholds are heuristics, not calibrated confidence probabilities. Similar frames cannot prove provenance or absence of anomalies.
- Comparison is limited to the final two seconds. Static scenes, lossy re-encoding, overlay changes and FPS conversions can cause ambiguous results.
- Container durations are diagnostic only; the previous `offline_ffmpeg_clip_end_audit.py` provides packet-PTS timing analysis.
- No edits to videos, no inferred hidden cards, and no automatic authorization for mathematical judgments.

## Next

- Add a synthetic throughput benchmark comparing full-decode vs indexed-seek extraction with varied GOP lengths, including the initial FFprobe indexing overhead.
- Connect temporal audit indicators to the offline review interface as **review required**, never as proof.
- Obtain an authorized annotated 3–5 minute recording to validate OCR and action reconstruction.