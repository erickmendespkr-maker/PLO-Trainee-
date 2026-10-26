# Cycle 127 — offline FFmpeg source/frame provenance (2026-10-26)

Scope: `docs/VIDEO_ANALYZER_SCOPE.md`; recorded PLO5/PLO6 sessions only. No live poker, bots or integration with gambling sites.

## Implementation

- Added `offline_ffmpeg_frame_provenance.py`, a command-line proof of concept accepting a **local recorded video**, an existing unverified contribution-ledger report, a strict frame-selection JSON, and a **new** output directory.
- Reads the source video twice with SHA-256 (before and after extraction), checks metadata with FFprobe, extracts selected decoded frames with FFmpeg `select`/`showinfo` and `crop`, and records **observed decoder PTS**, PNG crop hashes, video hash and duration.
- Generates `evidence_manifest.json` compatible with Cycle 126 `offline_action_evidence_link.link` and `provenance_status.json`. Confidence for recognition is **0.0** because no OCR was performed. All equity/EV gates remain closed.
- Rejects duplicate event indices, invalid frame/crop coordinates, timestamp drift >1.5s, unsafe source paths, existing output directory and changes in source bytes detected by the second hash. Failed operations remove their newly created output directory.
- Constraints: up to 16 frame requests per run, 2-hour duration, 12-GiB recording, 8-MiB PNG crop. Decoding by frame index is intentionally not optimized for hour-long videos; no guarantee against concurrent file replacement attacks. Only use trusted FFmpeg binaries and local recordings.

## Synthetic verification

- `python -m unittest -v test_offline_ffmpeg_frame_provenance` — **17/17 passed** locally with FFmpeg/FFprobe installed.
- Selected regression suite including Cycle 126 evidence links, contribution ledger, pot-limit bounds, triage and manual-review components, plus two VFR checks — **189/189 passed** locally. This is **not** the complete repository test suite.
- CLI smoke test used a 2-second synthetic 320×240, 10-FPS MPEG-4 recording. Extracted two PNG crops at decoded PTS **0.1 s** and **0.2 s** and verified SHA-256 against source bytes. These are synthetic visual patterns, not poker gameplay.
- Two extra tests passed with a synthetic variable-frame-rate video, including an end-of-file **frame extraction** (not MP4 clip-duration validation). The decoded PTS was checked against FFprobe frame timestamps.
- Source/test file blob hashes were compared with GitHub branch after publishing; no remote CI result or Windows UI validation was claimed.

## CLI

```sh
python video_analyzer/offline_ffmpeg_frame_provenance.py \
  synthetic_source.mp4 synthetic_contribution_report.json frame_requests.json new_crops_dir
```

Frame request example:

```json
{"schema_version":1,"frames":[{"event_index":0,"frame_index":1,"bbox_pixels":[0,0,160,120]}]}
```

`frame_index` is a zero-based **decoded** video-frame index, not a time in seconds. `bbox_pixels` is `[x,y,width,height]` in source pixels. The selected frame must have a decoder PTS within 1.5 seconds of the corresponding ledger event PTS. The output directory must not exist.

## Unverified and next

- Source SHA-256 verification does **not** establish that a human annotation, crop contents, card or action is correct. OCR accuracy and EV are not verified.
- No real annotated PLO5/PLO6 recording was available. 40–60-minute performance, four-table tracking, VFR/audio sync, full suite/CI and end-of-recording MP4 duration remain unverified.
- Next: use FFprobe frame/packet PTS and bounded interval decoding for efficient VFR/long recordings; verify end-of-file cut duration without synthesizing frames; test OCR and hand segmentation against an authorized annotated recording.
