# Cycle 129 — indexed seeking and terminal-frame visual diagnostics

Scope: `docs/VIDEO_ANALYZER_SCOPE.md`. Only authorized, prerecorded PLO5/PLO6 recordings; no live assistance, gambling-site connection, playable tables, credentials or paid services.

## Added

- `offline_ffmpeg_seek_frame_provenance.py`: FFprobe scans decoded-frame presentation timestamps once to map absolute frame indices. For each requested index, FFmpeg seeks to its PTS and the decoded `showinfo` PTS must match the index within 1 ms. Supports VFR and tested B-frame streams; preserves the existing evidence manifest schema and never authorizes equity/EV. Fails closed on incorrect seeks. **Not a measured performance improvement:** FFprobe still scans the whole recording and FFmpeg decodes each requested seek separately.
- `offline_ffmpeg_batch_frame_provenance.py`: opt-in `strategy="indexed_seek"`, leaving `full_decode` as the unchanged default. Provenance status records the extraction strategy, index pass and seek count.
- `offline_ffmpeg_clip_visual_audit.py`: compares the last decoded video frame of the source and clip as 256×144 grayscale thumbnails and combines it with existing packet-span timing diagnostics. Records pixel mean absolute error, source/clip hashes, and explicit uncertainty. Never claims video provenance or that a duplicated frame was ruled out. This is a *diagnostic*; lossy re-encoding, scaling and overlays can alter pixel differences.

## Verification (synthetic only)

- 10 new visual-audit tests, 9 new seek tests; **241 selected `test_offline_*.py` tests passed locally** after the changes, including prior regressions.
- VFR, B-frame, last-frame, duplicate-frame reuse, wrong seek PTS rejection, output cleanup, non-overwrite, symlink rejection, and re-encoded/remuxed clip tests.
- FFmpeg 7.1.5, Python 3.13.5; no CI or full-repository suite executed.
- No authorized PLO session video was supplied; real OCR accuracy, end-to-end reconstruction, equity/EV calibration, and hour-long throughput remain unverified.

## Next

- Benchmark indexed seeking against full decode on long recordings and varying GOP lengths; implement a persistent bounded frame index only if measurements justify it.
- Extend visual audit to preceding terminal frames and duplicate-frame detection, retaining conservative confidence and human review.
- Validate real recorded footage against annotated hands when available.
