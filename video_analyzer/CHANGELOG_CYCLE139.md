# Cycle 139 — offline reviewed decision timeline (2026-10-27)

## Scope

Adds `offline_reviewed_decision_timeline.py`, a **read-only, create-only** JSON
index of 1–40 independently generated `offline_reviewed_pipeline.py` result
folders. Only existing, human-approved, previously exported decisions receive
clip timestamps; blocked hands remain in the index with null decision times.
No automatic clip selection, gameplay, live assistance or platform integration.

## Provenance and checks

- Re-hashes every artifact listed in each `pipeline.json`, rejects unlisted
  files, symlinks, size discrepancies and missing files.
- Binds pipeline, handoff, Monte Carlo report, candidate hash, clip hash,
  recording identity, table/hand ID and manually approved timestamps.
- Rejects duplicate hand IDs, mixed recording claims, duplicate JSON keys,
  nonfinite numbers, unsafe paths and unsupported verification claims.
- Orders decisions deterministically and flags overlapping clip windows on
  the same table for human review (no conclusion about hand boundaries).
- Does not read raw recording bytes or independently verify frame PTS.
  Verified source SHA refers to the earlier clip export, not to this index run.
- Writes a new JSON file exclusively (`O_EXCL`), without touching inputs.

## Local tests

`python -m unittest -v test_offline_reviewed_decision_timeline.py`

20 synthetic tests passed on 2026-10-27. The fixtures contain fake MP4 bytes
and deliberately **do not** validate FFmpeg decoding, actual poker OCR or
end-to-end performance. Full repository suite and CI not executed.

## Blockers / next

No authorized real 3–5 minute annotated PLO5/PLO6 recording is available.
Next: validate this index against actual `offline_reviewed_pipeline` output,
then connect reviewed timestamps to the local session browser without
promoting manually entered observations to video-verified facts.
