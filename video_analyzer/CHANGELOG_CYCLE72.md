# Cycle 72 — Conservative consistency audit of human-reviewed hand timelines

## Scope

Added `activity_timeline_consistency_audit.py` to audit *existing* human-reviewed PLO5/PLO6 timelines, with up to four tables, without declaring OCR output to be poker truth. It flags possible board prefix/count inconsistencies, changes in visible private cards, board/private-card collisions, non-monotonic observation PTS, same-PTS conflicts, changing variant annotations, and apparent pot decreases. The latter can be legitimate payouts, side pots, UI changes or OCR mistakes, so are **review hints only**. Missing cards/board values are never filled from later observations.

## Usage

```bash
python video_analyzer/activity_timeline_consistency_audit.py reviewed_timeline.json audit.json
```

The CLI refuses to overwrite an existing file, checks the source timeline's status and provenance, and optionally pins its canonical digest with `--expected-timeline-sha256`. The output includes hand/observation indices, PTS timestamps, source-image references where available, and explicit manual-review flags. The output never authorizes equity, EV, automated hand boundaries, clip selection, or strategic error claims.

## Verification on synthetic inputs

- 10 new tests passed (plus 3 subtests).
- 73 selected integration/regression tests passed (plus 60 subtests), including the 10 new tests.
- Full-suite execution was attempted but did not finish within the execution limit. **No full-suite pass is claimed**.
- Four-table synthetic example emitted review flags for apparent pot drop, board mismatch, private-card change and board/private-card collision. This is **not** a recognition-accuracy measurement.

## Blockers

A 3–5 minute authorized recording is still required to calibrate real OCR and measure recognition against human annotations. No video truth, exact hand boundaries, opponent ranges, equity/EV conclusions or MP4 decision clips are verified by this audit.
