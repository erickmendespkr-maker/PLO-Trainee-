# Cycle 113 — Static, read-only offline review page (2026-10-26)

**Branch:** `feature/plo5-plo6-training` only. **Product:** offline/asynchronous review of user-recorded PLO5/PLO6 video, per `docs/VIDEO_ANALYZER_SCOPE.md`. No playable tables, opponents, real-poker integration, production, credentials or spending.

## Implemented

- `offline_clip_review_page.py` creates **one standalone HTML review page per manually selected MP4 clip** from the Cycle 111 `clip_math_provenance.json` association. It is a local *presentation-only* step, not an automatic analyzer.
- The page shows the local MP4 player, human-assigned table and hand ID, manually claimed source/decision timestamps, equity and its **sampling-only** 95% interval, modeled EV and its **sampling-only** interval, Monte Carlo trials/seed, subjective human confidence, opponent range combination count, model notes/limitations, source and clip hashes, and explicit non-verification warnings.
- An optional Cycle 112 `visual_alignment.json` adds **sampled visual MAE**, explicitly **not** frame-exact PTS proof. Cross-checks source/clip SHA-256 and human table identity. Rejects attempts to promote any verification or automation flags.
- HTML has **no JavaScript, external assets, network calls, forms, editable data or automatic clip selection**. User-controlled text is escaped; the video source is a percent-encoded local filename; a restrictive CSP is included.
- Requires output HTML to be a **new file beside the clip** (for a portable relative MP4 reference); uses exclusive create, private permissions, no-overwrite, bounded input/output sizes, duplicate JSON-key rejection, finite numeric validation, source-clip SHA-256 verification, symlink checks, and input rechecks before writing.
- The generator **does not** recalculate equity/EV, verify OCR or video content, claim hand/action boundaries, or modify any MP4. The `source_recording_sha256` is read from the upstream manifest and is not rehashed against the original recording in this step.

## CLI

```bash
python video_analyzer/offline_clip_review_page.py \
  exported_clip.mp4 clip_math_provenance.json new_review.html \
  --visual-report visual_alignment.json
```

The optional `--visual-report` may be omitted. Keep `new_review.html` in the same directory as `exported_clip.mp4`, then open the HTML file locally. Do not open untrusted third-party HTML files. The MP4 must be accessible beside the HTML file. This is a single-clip proof of concept, **not** yet a job queue, upload portal or multi-hand dashboard.

## Locally verified (synthetic only)

- `python -m unittest -v test_offline_clip_review_page`: **30 passed**. Includes actual FFmpeg-generated synthetic MP4, CLI export, optional visual report, four human table IDs/PLO6, XSS escaping, filename encoding, input integrity, malformed JSON, duplicate keys, symlink/no-overwrite protection, mismatched source/clip/table, and verification-flag rejection.
- `python -m unittest -v test_offline_clip_review_page test_offline_clip_visual_alignment test_offline_clip_frame_pts_audit test_offline_manual_clip_export`: **67 passed** (30 new + 14 + 17 + 6), using dependency files from the Cycle 112 local archive. The dependency Git blob SHAs match the target branch: `offline_manual_clip_export.py` (`39f3ef52d506f089afd920768715a9a90699644f`), `offline_clip_frame_pts_audit.py` (`f97fea2555a1f7a3b9a58bb2265b2a360f13d3ea`), `offline_clip_visual_alignment.py` (`9a1d3953bfaa34d7f6a58fd4762bb2712a18887b`). This is **selected regression**, not a full exact-branch suite.
- Executed CLI with the **actual synthetic Cycle 111 clip and provenance JSON** and **actual synthetic Cycle 112 visual JSON** from earlier local test artifacts; produced a static HTML page with visual report included. This is a presentation test against earlier synthetic artifacts, not real PLO footage.

## Not verified / blocked

- Full exact-branch test suite and remote CI; browser visual/manual usability and portability across Windows browsers; actual OCR, reconstructed hand boundaries, precise decoded-frame PTS, video upload and asynchronous job queue; full 40–60 minute four-table sessions.
- No authorized annotated 3–5 minute real PLO5/PLO6 recording. **Do not claim accuracy of real-hand reconstruction or automatic strategic verdicts.**

## Next cycle

1. Build a bounded **multi-hand offline review index** from multiple individually validated clip-link manifests, without exposing arbitrary file paths or enabling live behavior.
2. Add decoded-frame PTS measurement to the source/export correspondence audit and test CFR/VFR with known ground truth.
3. Validate the pipeline against an authorized annotated recording when available.
