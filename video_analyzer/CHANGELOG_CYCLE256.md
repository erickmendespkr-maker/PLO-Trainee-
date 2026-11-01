# Cycle 256 — offline reviewed math-to-clip navigation

## Scope
Introduces `offline_reviewed_math_clip_report.py`, joining a reviewed-clip
manifest, timestamp-scoped math candidate and Monte Carlo/EV report to **one**
matching MP4 decision segment. Produces local HTML + JSON; no live capture,
client integration, auto-OCR approval, betting or strategic correctness claim.

## Fail-closed safeguards
- Checks variant, table, hand, decision timestamp, clean human-review flags,
  and review/candidate SHA-256 provenance claims.
- Recomputes the conditional Monte Carlo report using the installed
  `offline_math_mc_bridge.build` and rejects mismatched or altered reports.
- Rejects missing/ambiguous clips, segments not containing the decision,
  omitted decision segments, malformed paths, changed media SHA-256,
  symlinks, duplicate JSON keys, changed source files and output collisions.
- Escapes HTML and displays range assumptions and the limits of Monte Carlo
  confidence. Does not authorize automated clip selection or a strategy verdict.
- Does **not** independently authenticate the original human review, OCR,
  source video, or accuracy of opponent ranges.

## Verification performed in local synthetic replay
- 15 new tests and 83 selected regression tests: **98/98 passed**.
- PLO5 and PLO6 synthetic candidates were linked to two actual 2-second MP4
  files created with FFmpeg and inspected with FFprobe; HTML/JSON generated.
- This local test used the `offline_omaha_equity_mc.py` engine snapshot bundled
  in cycle 255. Its local Git blob SHA is `91d25699893ba91bd644186c759b0c8964fb8423`,
  while the exact repository engine SHA is
  `c8229950ea35542000a038e4251d93c3baed5b15`.
  **The exact GitHub engine was not executed in this replay**. The adapter,
  existing math bridge, and reviewed-clip manifest matched the GitHub blob SHAs
  inspected during this cycle.
- No real poker recording, full 40–60 minute session, Windows validation,
  or full repository test suite was run.

## Reproduce on the authorized branch
```bash
cd video_analyzer
python -m unittest -v test_offline_reviewed_math_clip_report test_offline_math_mc_bridge test_offline_math_input_gate test_offline_math_decision_snapshot test_offline_call_ev_from_counts
python offline_reviewed_math_clip_report.py reviewed_clip_manifest.json timestamp_scoped_candidate.json internal_mc_report.json split_dir empty_output_dir
```

## Blockers / next
An authorized, annotated 3–5 minute PLO5/PLO6 recording is still needed to
measure OCR and hand reconstruction precision. Execute this integration against
the **exact** repository engine, then benchmark four-table long sessions.
