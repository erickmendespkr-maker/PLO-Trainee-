# Cycle 87 — preserve interior boundary uncertainty (2026-10-25)

Scope: `docs/VIDEO_ANALYZER_SCOPE.md`. Offline/asynchronous recorded PLO5/PLO6 only. No live poker, playable tables, automated bets, credentials, production changes or paid services.

## Implemented

- `boundary_history_bridge.py` now exports **schema_version 2** for navigation-only spans. It retains interior OCR boundary candidates (pending, uncertain, rejected), their window timestamps and reviewed frame provenance. Unresolved candidates are flagged instead of being silently treated as absence of a hand transition.
- Human-reported boundary endpoints include source task IDs, human timestamps, selected PTS-byte-matched frame IDs, PNG hashes (when provided), seek/decoded PTS metadata (when provided), and `independently_verified: false`.
- Validation rejects invalid table IDs, duplicate task/frame/annotation IDs, non-finite or out-of-window times, inconsistent pending counts, unsupported verdicts, unconfirmed asserted timestamps, overlapping confirmed windows, mismatched packet digests, non-false mathematical readiness claims, duplicate JSON keys and unsafe symlink input/output paths.
- `test_boundary_history_bridge_interior.py` adds 10 deterministic tests for interior uncertainty and adversarial inputs; original bridge fixture was brought into agreement with the upstream versioned review packet.
- No hidden cards, action sequences, hand IDs, equity, EV or strategic mistakes are inferred. Even spans with no unresolved interior candidates remain **unverified navigation spans**.

## Local verification

- 16 bridge tests passed (6 existing + 10 new), including FFmpeg/PTS review-handoff integration on **synthetic** frames.
- 95 selected tests passed in 32.937 seconds, covering boundary handoff, OCR boundary triage, temporal OCR, visual evidence, PTS audit, mathematical readiness and clip context. Suites overlap; 95 is the selected suite count, not a full-project total.
- Remote CI, full suite, real poker OCR accuracy, 40–60 minute sessions and end-to-end MP4 clip quality were **not verified**.
- The first demonstration uses only synthetic JSON candidates, not a real recorded poker session.

## API and limitations

```python
from boundary_history_bridge import export
result = export('review_packet.json', 'review_labels.json', 'navigation_spans.json')
```

Input packet and labels are schema version 1; output navigation report is schema version 2. Downstream consumers must explicitly support version 2. `contains_unresolved_interior_candidates` flags only the candidate windows known to the input; absence of such windows does **not** prove that a hand is complete. The PTS audit supports image timing/provenance only, not a verified poker action.

## Blocker / next

An authorized 3–5 minute PLO5/PLO6 recording and independent human annotations remain missing. Next: create a formal human-review hand-history draft from these spans, preserving every unknown card/action/amount; then validate against annotated recordings before mathematical gating or automatic clip ranking.
