# Cycle 257 — exact GitHub Monte Carlo engine verification and four-table synthetic benchmark

## Scope
The **exact** `video_analyzer/offline_omaha_equity_mc.py` blob from the authorized branch was reproduced in an isolated local test directory. Its calculated Git blob SHA matched GitHub: `c8229950ea35542000a038e4251d93c3baed5b15`. This resolves the engine-hash mismatch documented in cycle 256.

No source changes were made to the existing equity engine, `main`, production, credentials, or paid infrastructure.

## New components
- `offline_mc_four_table_benchmark.py`: deterministic, synthetic four-table (PLO5/PLO6/PLO5/PLO6) sequential benchmark using the installed original Monte Carlo engine. It logs seeds, input scenario SHA-256, original engine Git blob SHA, equity, Hoeffding sampling intervals, win/tie/loss counts and elapsed time. It does not authorize a strategy verdict.
- `test_offline_mc_four_table_benchmark.py`: ten regression tests for reproducibility, valid hands/ranges, result contract, confidence bounds, bounds enforcement and no-overwrite output.

## Locally verified
- **134/134 selected tests passed** against the byte-identical GitHub Monte Carlo engine (124 prior selected integration/regression tests plus 10 new benchmark tests).
- Four synthetic tables, **1,000 trials each**, sequentially processed: **4,000 total trials in 9.042684 seconds** in this particular local container. PLO5 table durations were 1.846573 and 1.846901 s; PLO6 were 2.698134 and 2.651076 s.
- Engine Git blob SHA: `c8229950ea35542000a038e4251d93c3baed5b15`.
- The two new Python files were published to the authorized branch and their Git blob SHAs matched the locally tested files.

## Reproduce (offline, no GitHub Actions)
```bash
cd video_analyzer
python -m unittest -v test_offline_mc_four_table_benchmark test_offline_math_mc_bridge test_offline_math_input_gate test_offline_math_decision_snapshot test_offline_call_ev_from_counts test_offline_reviewed_clip_manifest test_offline_reviewed_math_clip_report
python offline_mc_four_table_benchmark.py new_benchmark.json --samples 1000
```

## Limitations
The benchmark covers **mathematical throughput only**. No video was processed in this benchmark, no OCR precision was measured, and no 40–60 minute four-table session was tested. Timings are hardware-specific and not a deployment capacity guarantee. The Hoeffding interval quantifies Monte Carlo sampling uncertainty conditional on the supplied hypothetical ranges, not the uncertainty of visual recognition, opponent ranges or future betting. No Windows or full repository suite run.

## Blockers and next cycle
An authorized, annotated 3–5 minute PLO5/PLO6 video remains necessary for the first real visual accuracy evaluation. Next: benchmark FFmpeg sampling and four-table ROI segmentation on longer synthetic recordings; then integrate confirmed OCR/manual corrections with the now-verified exact engine and reviewed MP4 reports.
