# Cycle 114 — Bounded offline multi-hand review index (2026-10-26)

**Branch:** `feature/plo5-plo6-training` only. **Scope:** offline/asynchronous user-recorded PLO5/PLO6 sessions, per `docs/VIDEO_ANALYZER_SCOPE.md`. No playable tables, AI opponents, live integrations, credentials, production or spending.

## Added

- `offline_session_review_index.py` builds a **static, read-only HTML session index** for 1–40 *manually selected and linked* MP4 clips, covering up to four human-assigned tables. Clips are displayed in ascending **human-reported decision timestamp** order. It does not detect, rank or select hands automatically.
- Every clip's SHA-256 is verified against its Cycle 111 provenance JSON using the Cycle 113 validation rules. Optional Cycle 112 visual reports must match source, clip and table identity; they are **sampled similarity only**.
- All entries must belong to the same `job_id` and declared `source_recording_sha256`. Duplicate `(table_id, hand_label)` identities, duplicate filenames, mismatched source/job, false verification claims, malformed JSON, symlinks and path traversal are rejected.
- Only same-directory, regular local MP4/JSON inputs and a **new** same-directory HTML output are accepted. HTML escapes user text and percent-encodes MP4 names, has a restrictive CSP, no JavaScript, no forms, no network requests, and uses `preload=none`. Input SHA-256 is rechecked before exclusive output creation.
- The page shows source timestamps, equity, sampling-only 95% interval, modeled EV, subjective human confidence, Monte Carlo trial count/seed, model assumptions/limitations, and provenance hashes. All strategic claims remain explicitly hypothetical.

## CLI

Place the manifest, clips and per-clip provenance JSON in one directory:

```json
{
  "schema_version": 1,
  "session_label": "Sessão de revisão manual",
  "entries": [
    {"clip": "table1_hand1.mp4", "link": "table1_hand1_link.json"},
    {"clip": "table2_hand2.mp4", "link": "table2_hand2_link.json", "visual": "table2_hand2_visual.json"}
  ]
}
```

Run:

```bash
python video_analyzer/offline_session_review_index.py session.json session_index.html
```

The source `clip_math_provenance.json` is produced by the earlier manual workflow; it cannot be replaced with arbitrary mathematical claims. The HTML and MP4s must remain beside one another for offline playback.

## Locally tested (synthetic only)

- `python -m unittest -v test_offline_session_review_index`: **23 passed**, including actual FFmpeg-generated MP4, four-table ordering, corrupted media, duplicate hands, invalid verification flags, path traversal, symlinks, output overwrite, HTML escaping, filename encoding, source/job consistency and 40-entry limit.
- `python -m unittest -v test_offline_session_review_index test_offline_clip_review_page`: **53 passed** (23 new + 30 from Cycle 113). These are **selected local tests**, not the full exact-branch suite.

## Not verified / blocked

- No annotated authorized real PLO5/PLO6 footage; no OCR accuracy, real hand boundaries, automatic selection, precise decoded-frame PTS or full 40–60 minute session performance validation.
- Static page presentation and MP4 playback were not manually tested in Windows browsers. The index does not independently recompute Monte Carlo or verify the truth of the declared original source digest.
- Remote GitHub CI and the full exact-branch suite were not run.

## Next cycle

1. Verify actual decoded-frame PTS in source and exported clip with CFR/VFR synthetic fixtures.
2. Add a manual review state layer for uncertain OCR/hand boundaries, keeping explicit human confirmation and provenance.
3. Validate against a short authorized annotated recording when available.
