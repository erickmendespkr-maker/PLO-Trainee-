# Cycle 89 — conservative evidence lookup for manual hand annotations (2026-10-25)

Scope: `docs/VIDEO_ANALYZER_SCOPE.md`. Offline/asynchronous user-uploaded PLO5/PLO6 recordings only. No live play, real poker integrations, credentials, deployment or spending.

## Implemented

- `hand_evidence_link.py` cross-checks the original boundary packet, navigation spans, and reviewed hand-history report. The review is revalidated using the existing `boundary_hand_draft` validator, including immutable span metadata and no-math authority flags.
- For each manually annotated field/action, finds PTS-byte-matched **candidate** boundary PNGs from the same table, within the same provisional span and within 0.25 seconds of the annotation. Reports separate statuses for nearby frames, absent nearby frames, unknown values and hypotheses.
- Verifies the packet/navigation SHA-256 chain and rehashes local PNG bytes; rejects symlinks, mismatched digests, cross-table references, unsafe paths, duplicate tasks, missing matched PTS and forged math authority. The lookup does **not** independently re-decode the original video or verify the content of cards/actions.
- Retains all `ready_for_equity_or_ev`, `cards_or_actions_verified`, and automatic-clip authorization flags as `false`. Missing visual references never become invented facts.
- `test_hand_evidence_link.py`: 14 deterministic synthetic tests.

## Local verification

- 14 new synthetic tests passed.
- 54 selected tests passed in 14.562s, including existing FFmpeg-based upstream tests. The 54 include the 14 new tests.
- No real poker video, full test suite, remote CI, hour-long video, equity/EV end-to-end or automatic MP4 explanation was verified.

## Usage

```sh
python video_analyzer/hand_evidence_link.py navigation.json boundary_packet.json reviewed_hand_report.json boundary_visual_evidence/ evidence_lookup.json
```

The `boundary_visual_evidence/` folder must contain the original PNGs referenced by the packet. A matched frame is **only a navigation aid**: it does not prove that an annotation is correct. `no_nearby_byte_matched_frame` explicitly identifies where additional frame extraction/review is needed.

## Blocker / next

An authorized 3–5 minute PLO5/PLO6 video with independent hand annotations is still needed for accuracy evaluation. Next: generate bounded on-demand action-timestamp stills from the video and independently audit decoded PTS, then attach them to the manual review interface without promoting OCR guesses to facts.
