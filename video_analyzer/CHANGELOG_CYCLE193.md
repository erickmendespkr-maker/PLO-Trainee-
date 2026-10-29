# Cycle 193 — Offline audited card-frame gallery

Scope: `docs/VIDEO_ANALYZER_SCOPE.md`; recorded sessions only. No live poker, gameplay, real-money integrations, production changes or GitHub Actions.

## Added
- `offline_audited_card_gallery.py`: generates a local HTML gallery from the prior FFmpeg frame audit and human card review; lists each declared card, extracted PNG and requested timestamp.
- Each card requires explicit human acknowledgement plus free-form notes before the browser exports a local JSON confirmation.
- A separate verifier checks SHA-256 of manifest, manual review, PNGs and exported acknowledgement, rejects changed associations and incomplete confirmations, and emits a conservative JSON report.
- `test_offline_audited_card_gallery.py`: 16 FFmpeg-backed synthetic tests, including tampering, symlinks, path traversal, mismatched timestamps, incomplete reviews and output overwrite prevention.

## Reproduction
From `video_analyzer`:

```bash
python -m unittest -v test_offline_audited_card_gallery
python offline_audited_card_gallery.py generate /path/to/snapshots /path/to/manual_review.json /path/to/snapshots/gallery.html
# Open gallery.html in a local browser, inspect each PNG and export snapshot_confirmation.json.
python offline_audited_card_gallery.py verify /path/to/snapshots /path/to/manual_review.json /path/to/snapshot_confirmation.json /path/to/new_acknowledgement_report.json
```

## Limitations
The verification only proves source-file integrity and records the **human assertion**. It cannot prove that a declared card is actually visible or that OCR was correct. It does not determine player identity, decoded-frame PTS, equity correctness or strategic action quality. A real authorized annotated PLO5/PLO6 recording is still needed to measure recognition accuracy. Direct `file://` Chromium navigation is blocked in the test environment; JavaScript interactions were exercised by loading HTML in memory, without confirming PNG loading via browser. Windows and 40–60 minute sessions remain untested.
