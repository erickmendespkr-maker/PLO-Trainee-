# Cycle 236 — offline conditional-EV MP4 excerpt with visible caveats

## New component

`video_analyzer/offline_ev_decision_clip.py` exports one **offline** MP4 excerpt
with a burned-in explanation and a SHA-256-bound JSON report. It does not
observe poker live, play hands, or infer strategic mistakes.

```
python video_analyzer/offline_ev_decision_clip.py \
  SUMMARY.json EV.json DECISION.json RECORDED_VIDEO.mp4 OUT_DIR CLIP_ID
```

The source `SUMMARY.json` is the cycle-232 *unverified* hand/visual summary;
`EV.json` is the cycle-235 *conditional* EV output. The video must be the exact
file whose SHA-256 is claimed by the summary and EV report. The manual
`DECISION.json` has the following strict schema:

```json
{
  "schema_version": 1,
  "source_summary_sha256": "<SHA-256 of SUMMARY.json>",
  "source_ev_sha256": "<SHA-256 of EV.json>",
  "hand_id": "H1",
  "table_id": "T1",
  "decision_pts_seconds": 2.0,
  "action_taken_claim": "raise",
  "action_origin": "manual_review_unverified",
  "reviewer_confidence_claim": 0.6,
  "notes": "Reviewer manually noted this action and its timestamp; this is not authenticated.",
  "clip_before_seconds": 1.0,
  "clip_after_seconds": 2.0
}
```

The decision timestamp must be within 0.5 seconds of an **action** field
marked `seen_by_reviewer` in the source hand summary. This is still a human
claim, not semantic proof that the video contains the action. Nearby card
observations cannot substitute for action evidence.

## Selection and uncertainty

The model recomputes EV accounting consistency for fold/call/check and any
optional heads-up raise before ranking a single decision. The conditional
priority gap is the difference between the largest modeled EV and the modeled
EV of the declared action, in chips. It is **not actual regret**, not a
recommendation, and does not account for alternative ranges or future action.
Reviewer confidence is self-reported and **not calibrated**; it is not used as
an objective probability or to claim an error. For a raise, fold probability
and called equity remain independent assumptions; no raise confidence interval
is invented. The call interval covers Monte Carlo noise only.

The MP4 overlay explicitly says the action and ranges are unverified, and the
JSON sidecar contains assumptions, Monte Carlo seed/count, source hashes,
clip timestamps, conditional action EVs and limitations. FFmpeg and ffprobe
are invoked locally without a shell; outputs must be new, and the source video
is rehashed after rendering. No cloud services, credentials or live integration.

## Verification and known limitations

Tests cover provenance mismatches, altered EV formulas, impossible timestamps,
missing action evidence, unverified statuses, invalid confidence, selected
unmodeled actions, overwrite refusal, and an actual FFmpeg-generated MP4
with burned-in overlay from a **synthetic** five-second video. This does not
validate OCR, genuine action recognition, the original video's authenticity,
Windows compatibility, 40–60-minute processing, or the full repository suite.
A real authorized, annotated 3–5-minute recording remains missing.

The CLI emits **one clip per run**. Multi-hand ranking and automatic selection
across four tables remain future integration work.
