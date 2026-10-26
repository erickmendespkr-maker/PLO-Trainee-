# Cycle 112 — Bounded source ↔ exported MP4 visual comparison (2026-10-26)

**Only branch:** `feature/plo5-plo6-training`. **Scope:** `docs/VIDEO_ANALYZER_SCOPE.md`; recorded offline video, no playable poker tables, live integration, credentials, production or spending.

## Implemented

- `offline_clip_visual_alignment.py` samples three decoded positions from a human-selected exported MP4 and compares each against three bounded nearby seeks in the original recording, applying the same manually selected table crop when present.
- FFmpeg decodes 32×32 grayscale samples and reports normalized mean absolute difference (MAE), candidate seek times and the lowest-MAE candidate. Source and clip SHA-256 digests are verified against the original export sidecar; geometry, durations, zero-origin PTS policy, manual table identity and non-authorization flags are validated. Rechecks media and sidecar bytes before exclusively writing JSON.
- The output explicitly states that sampled visual similarity **does not** verify frame-exact PTS, action/hand boundaries, OCR, hidden cards, Monte Carlo results, EV or strategic errors. Static scenes may match at incorrect times. No clips are automatically selected and no source or exported MP4 is modified.
- The module is intentionally bounded: 3 clip samples × 3 source seeks, without decoding full 40–60-minute recordings. Uses only Python stdlib, FFmpeg and FFprobe.

## Verified locally

- `python -m unittest -v test_offline_clip_visual_alignment`: **14 passed**. Synthetic CFR, VFR, crop, four manual table identifiers, nonzero-origin PTS rejection, source/clip digest tampering, symlink and duplicate-key rejection, geometry mismatch, fail-closed on FFmpeg errors, no-overwrite and source-change detection.
- `python -m unittest -v test_offline_clip_visual_alignment test_offline_clip_frame_pts_audit test_offline_manual_clip_export`: **37 passed** (14 + 17 + 6). `python -m py_compile` of new code/tests passed.
- Local dependency Git blob SHA matches the target branch: `offline_manual_clip_export.py` (`39f3ef52d506f089afd920768715a9a90699644f`) and `offline_clip_frame_pts_audit.py` (`f97fea2555a1f7a3b9a58bb2265b2a360f13d3ea`). This is **selected regression**, not a full exact-branch checkout.
- Ran the new CLI against the previously generated 12-second **synthetic** recording and 2-second clip from Cycle 111: 3 sampled positions, mean best normalized grayscale MAE **0.002825**. This is a synthetic image-similarity measurement, **not** a frame-exact verification.

## Not verified / blockers

- Full exact-branch suite, remote CI, authentic poker footage, real hand/action boundaries, field-level OCR precision, full one-hour pipeline and true PTS-to-PTS output alignment. The current FFmpeg seek sampler does **not** measure actual decoded frame PTS; VFR can shift its sample positions.
- No authorized annotated 3–5-minute PLO5/PLO6 recording available; continue with independent components and synthetic tests.

## Next

1. Add actual decoded-frame PTS instrumentation and a source/export frame correspondence index; distinguish VFR seek artifacts from genuine mismatches.
2. Build a local read-only review page showing the linked MP4, human hand ID, sampling confidence, Monte Carlo assumptions/CI and explicit non-verification notices.
3. Validate against annotated authorized footage before claiming OCR or hand reconstruction accuracy.

### CLI

```bash
python video_analyzer/offline_clip_visual_alignment.py \
  recording.mp4 exported_clip.mp4 exported_clip.json new_visual_audit.json
```

Inputs are local, output must not already exist. No real-money or live-poker integration.