# Cycle 97 — offline mathematical report (2026-10-25)

Scope: `docs/VIDEO_ANALYZER_SCOPE.md`. Work restricted to `feature/plo5-plo6-training`.

## Implemented

- `hand_math_report.py`: static, read-only Portuguese HTML summarizing hypothetical PLO5/PLO6 equity and EV, 95% **sampling-only** confidence intervals, human-estimated observation confidence, manual cards, pot, call/raise assumptions, sample opponent range, model notes and limitations.
- Recomputes the bounded seeded Monte Carlo scenario using the original intake and manually completed worksheet; rejects a modified mathematical result, mismatched metadata and changed input files.
- Embeds SHA-256 of all three JSON sources; does not claim source authenticity, video verification or a strategic error. CSP blocks scripts and external resources. HTML escapes human-entered text. Does not overwrite existing files.
- `test_hand_math_report.py`: 13 new synthetic tests for four-table summaries, PLO5/PLO6, blocked cases, HTML escaping, deterministic reproduction, modified math, hashes, symlinks, duplicate JSON keys and no-overwrite.

## Verified locally

- 13 new tests: PASS.
- 91 selected tests across report, scenario, intake, visual-history, visual-verdicts and FFmpeg evidence: PASS (8.3 s).
- `compileall` for both new Python files: PASS.
- Four-table synthetic report: 2 hypothetical, 1 blocked, 1 skipped; no real hands processed.
- Local Chromium headless browser test: **inconclusive** (environment timeout); do not claim visual browser compatibility.

## Not verified / blockers

- Full test suite, remote CI, 40–60 minute sessions, real video OCR/hand reconstruction, complete end-to-end MP4 clips.
- Missing authorized 3–5 minute PLO5/PLO6 recording and human annotations for real-world recognition metrics.
- Math is heads-up all-in simplified: no rake, side pots, ICM, or future betting. Monte Carlo intervals exclude range/model/OCR uncertainty.

## Usage

From `video_analyzer/`, after generating a mathematical JSON via `hand_math_scenario_run.py`:

```sh
python hand_math_report.py original_intake.json completed.json math_result.json new_report.html
```

Open `new_report.html` offline. All three JSON files must match the original calculation; a modified report input fails closed.

## Next

Add an explicit reviewer-selected clip candidate workflow linked to hypothetical math results, without automatic error claims, and validate MP4 generation using synthetic FFmpeg video. Prioritize a real authorized sample when supplied.
