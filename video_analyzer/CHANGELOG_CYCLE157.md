# Cycle 157 — conditional EV + offline FFmpeg clip proof of concept

Branch: `feature/plo5-plo6-training`. Scope: `docs/VIDEO_ANALYZER_SCOPE.md`.

## Delivered

- `offline_omaha_conditional_ev.py`: independent, explicitly hypothetical heads-up terminal-showdown model for **fold, call and raise**. It recomputes Monte Carlo equities from separate user-declared opponent combinations for call and raise-called, using the existing PLO5/PLO6 engine.
- Pot and contributions are in a single consistent unit, represented with decimal arithmetic. Fold EV is zero from the decision point. Call EV = `equity_call * (pot_before + call_cost) - call_cost`. Raise EV = `fold_probability * pot_before + (1 - fold_probability) * (equity_raise_called * (pot_before + raise_total + raise_total - call_cost) - raise_total)`.
- Includes independent MC sampling bounds for call and a sensitivity envelope for raise using the user-declared fold-probability interval. **Not** a joint 95% confidence region or a measure of range-model error.
- Rejects unsupported models: multiway, side pots, nonzero rake, future betting, incomplete or inconsistent assumptions, malformed/duplicated cards, out-of-range probabilities, unsupported amounts, and unverified raise legality claims. Raise size is only screened against a conservative pot-limit cap; min-raise, stack and full legality are **not** established.
- `offline_reviewed_clip_export.py`: independent offline FFmpeg/ffprobe MP4 exporter for reviewer-selected timestamps and an even-pixel crop from a local MP4/WebM recording. Requires human approval and SHA-256 binding to the video. Writes a new MP4 **without audio** and a `.mp4.json` sidecar containing the explanation, source hash, clip hash, timestamps, ROI and limitations. No automatic hand selection or claims of verified video evidence.
- Rejects symlinked inputs, existing outputs, mismatched source hash, invalid timestamps, invalid ROI, malformed JSON and unapproved requests. Never connects to a poker service.

## Verification

Run from `video_analyzer/` with Python 3 and FFmpeg/ffprobe installed:

```sh
python -m unittest -v test_offline_omaha_conditional_ev test_offline_reviewed_clip_export test_offline_omaha_equity_mc test_offline_omaha_equity_known_cases
python -m py_compile offline_omaha_conditional_ev.py offline_reviewed_clip_export.py
```

**88 selected tests passed locally** after publishing the four source/test files: 31 new EV tests, 21 new clip tests, and 36 existing Monte Carlo tests. Git blob SHA hashes of the four published Python files were compared to the local files and matched. No GitHub Actions.

Synthetic examples:
- PLO5 flop, 100 MC samples per action with different seeds, pot 100, call 20, raise 60, assumed fold probability 25%: conditional fold EV 0.00, call EV +35.20, raise EV +55.00. This is an artificial scenario with one hypothetical villain hand; it is **not** a recommendation or poker-game prediction.
- 3-second 640x360 generated test-pattern recording, cropped table 3 ROI (0,180,320,180) from 0.5 to 2.5 seconds: valid 2.0-second 320x180 MP4 and SHA-256-bound explanation JSON sidecar. Four ROI positions were covered by automated tests.

## Not verified / blocked

- No authorized annotated real poker recording has been supplied. OCR accuracy, hand boundaries, actual player actions and real 40–60 minute performance are unverified.
- No end-to-end pipeline from reviewed video hands to EV and automatic clip selection. The EV model intentionally has no direct OCR/hand bridge yet.
- No user interface, subtitle overlay, audio preservation, or 60-minute clip throughput test. Explanations are JSON sidecars, not text burned into the MP4.
- Full repository test suite and production deployment not run.

## Next

Bind EV requests to independently reviewed pot/action snapshots with hash-linked human approval. Build an offline queue for batch video processing and add human-reviewable hand-to-clip selection; preserve the fail-closed gates until accuracy on real annotated video is measured.
