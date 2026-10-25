# Cycle 106 — offline hand reconstruction checklist (2026-10-25)

## Scope
Only `feature/plo5-plo6-training`. Offline/async analysis of user-recorded PLO5/PLO6 sessions, without live poker integration or playable tables.

## Implementation
- `offline_job_hand_reconstruction_checklist.py` consumes the **unverified** `human_hand_evidence_dossiers.json` produced in Cycle 105 and creates a separate JSON task queue for human reconstruction.
- Validates dossier identity, nominal intervals, SHA-256 fields, counts, statuses, field summaries, cross-table references, simultaneous conflicts, and no-math authority gates. Rejects tampering that is detectable from the dossier's internal structure.
- Preserves original source-image hashes and separate categories: no approved observation, unresolved OCR, conflicting same-timestamp observations, and expected temporal changes that require action-sequence interpretation.
- Emits blank, non-authoritative manual templates (PLO variant, cards, streets, pot, stacks, actions, ranges, exact video PTS, independent attestation). **No OCR values are promoted to mathematical facts.**
- Exports JSON with `O_EXCL` (no overwrite) and size limits. Source remains unchanged.

## Verification
- `python -m pytest -q test_offline_job_hand_reconstruction_checklist.py`: 27 passed.
- `python -m pytest -q test_offline_job_hand_reconstruction_checklist.py test_offline_job_hand_evidence_dossier.py test_offline_job_hand_interval_review.py test_offline_job_review_timeline.py test_offline_job_review_windows.py test_offline_job_review_decisions.py test_offline_job_review_handoff.py test_offline_job_evidence_audit.py test_offline_jobs.py`: 195 passed, 28 subtests passed.
- Expanded local suite including mathematical scenario, report and clip tests: **267 passed, 90 subtests passed**.
- Four-table, nominal 60-minute JSON-only benchmark: 4,800 observations, 120 dossiers; dossier preparation 0.1775 s and checklist generation 0.0346 s on this runner. No video decoding/OCR was measured.
- The upstream modules from Cycles 99–105 were hash-matched to the target branch, **except** `offline_jobs.py`, which differs in the local Cycle 98 snapshot. Thus this is not a full exact-tree regression.
- All tests are synthetic. No real poker session or OCR accuracy benchmark was used.

## Limits / next steps
- This validates **internal consistency**, not cryptographic authenticity of arbitrary external JSON. For genuine provenance, generate dossiers through `dossiers_job()`, which re-audits the original recording and evidence.
- Nominal sampling timestamps are **not** exact source PTS.
- No hand is reconstructed or mathematically authorized, and no automatic clips are selected.
- Next: independently attested manual action sequences and source PTS; then guarded hand-to-math scenario binding and end-to-end synthetic clip tests.
- Blocking sample: an authorized, annotated 3–5 minute PLO5/PLO6 recording is still missing.
