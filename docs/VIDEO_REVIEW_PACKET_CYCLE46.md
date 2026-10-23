# Offline decision review worksheet (cycle 46)

This feature belongs to the recorded-video-only PLO5/PLO6 analyzer. It does **not** recognize poker hands from video or execute equity/EV calculations.

## Run locally

From the repository root, after creating a human-reviewed activity decision queue with activity_snapshot_chain.py:

    python video_analyzer/activity_review_packet.py queue.json worksheet.html blank_review.json

Outputs:
- worksheet.html: read-only, printable review hints for up to four tables. The HTML has no scripts, external assets, or embedded local image links.
- blank_review.json: an **unconfirmed** form with all required decision fields, call ranges, and model assumptions unset.

The queue SHA-256 is recorded so a reviewer can pin the exact input. This digest is **not** proof that the original recording or image bytes are authentic. Re-audit original media before any human attestation.

## Fail-closed checks

Rejects EV-ready input, unconfirmed queue identity, malformed timestamps, same-frame/future observations used as earlier hints, duplicate task IDs, unsafe image paths, and attempts to overwrite output files. Escapes all untrusted strings in the generated HTML.

## Verified

11 new focused unit tests and 584 local tests total passed using synthetic four-table evidence. No remote CI execution or real-video recognition accuracy is claimed.

## Next

Build a human editing/confirmation interface, then require explicit provenance and range assumptions before producing conditional equity/EV and annotated MP4 clips. A consented 3–5 minute sample remains necessary for real recognition calibration.
