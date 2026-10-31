# Cycle 237 — offline conditional-EV batch clip selection

Scope: `docs/VIDEO_ANALYZER_SCOPE.md`. This module is strictly offline/asynchronous. It does not play poker, capture live tables, connect to poker services, infer hidden cards, or treat OCR as mathematical truth.

## Added

- `offline_ev_batch_clips.py`: preflight a batch of independently reviewed decisions and their separately computed EV JSONs against a single source-video hash and a single unverified visual summary. Uses the existing `offline_ev_decision_clip.validate` accounting/evidence rules and its FFmpeg overlay renderer.
- Deterministic priority: descending **conditional gap to the highest modeled action EV in chips**, ties by timestamp, table, hand, clip ID. Reviewer confidence is recorded but **never treated as calibrated probability or used to rank**. All numbers depend on manually supplied ranges and simplified EV assumptions.
- Up to 40 candidates from up to four tables, up to 20 output MP4s per batch. Suppresses overlapping clips **within the same table**; permits simultaneous events from different tables. A user-specified minimum modeled gap and maximum clip count can exclude candidates, with reasons preserved.
- Preflight of every entry before writing; basename-only JSON references, no symlinked JSON files, immutable SHA-256 source bindings, duplicate decision/ID rejection, no output overwrites. On rendering or post-render validation failure, removes only newly generated files.
- `batch_report.json`: ordered selected clips, skipped entries/reasons, hashes, timestamps, manual confidence claims, explicit model limitations. Each MP4 also has its individual JSON report.

## Invocation

```
python video_analyzer/offline_ev_batch_clips.py SUMMARY.json SESSION.mp4 BATCH.json NEW_OUTPUT_DIRECTORY
```

`BATCH.json` must contain exactly:

```json
{
  "schema_version": 1,
  "status": "manual_offline_decision_batch_unverified",
  "max_clips": 10,
  "min_gap_chips": 1.0,
  "entries": [
    {"ev_json": "H1_EV.json", "decision_json": "H1_DECISION.json", "clip_id": "T1-H1"}
  ]
}
```

The EV/decision JSON files must be direct siblings of `BATCH.json`. The output directory must already exist. Existing outputs are never overwritten. FFmpeg and FFprobe must be installed.

## Synthetic verification

- Run `python -m unittest -v test_offline_ev_batch_clips.BatchTests` from `video_analyzer`.
- Regression suite: run the five test classes `ContractTests`, `EquityTests`, `ActionEVTests`, `ClipTests`, `BatchTests`.
- Tests use generated color-pattern videos, manual action evidence claims and hypothetical PLO5 EV data. They do **not** measure OCR precision, accuracy of action identification, or decision quality in real poker sessions.

## Remaining limitations

- Source video is not semantically checked. The exported MP4 is a **full-frame excerpt**, not a per-table crop; table IDs are manual claims.
- Rankings across tables use absolute modeled chip EV gaps; chip sizes/stakes and the model assumptions may not be comparable across tables. This is a triage queue, **not** a verified error ranking.
- Monte Carlo intervals do not cover range, OCR, action or model uncertainty; raise EV has no calibrated interval.
- No validation with real authorized 3–5 minute recordings, 40–60 minute sessions, Windows or full repository test suite. A short authorized, annotated video remains necessary for visual accuracy evaluation.
