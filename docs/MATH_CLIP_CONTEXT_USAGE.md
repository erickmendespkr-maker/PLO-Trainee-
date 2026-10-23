# PLO Trainee — conditional math sidecars for human-selected clips

This component connects **human-selected** recorded-video review clips to a **separately requested hypothetical** PLO5/PLO6 heads-up all-in call calculation. It never treats a conditional calculation as verified video evidence or ranks clips by EV.

## Inputs and output

The CLI requires (in order):

1. `review_clip_manifest.json` from `activity_review_clip_export.py`.
2. The directory containing the original exported MP4s.
3. `scenario_worksheet.json` from `activity_scenario_worksheet.py`.
4. A separately supplied request JSON for `activity_hypothetical_math.py` (explicit weighted opponent range, seed, trials and model acknowledgement).
5. The corresponding report from `activity_hypothetical_math.py`.
6. A **new** output path for the sidecar JSON.

Run from `video_analyzer/`:

```bash
python activity_math_clip_context.py \
  review_clip_manifest.json clips/ scenario_worksheet.json \
  hypothetical_request.json hypothetical_report.json clip_math_context.json
```

The module checks the source recording, queue and draft hashes across the worksheet and clip manifest; verifies the actual MP4 hashes, sizes and decoded metadata; checks decision identity, timestamp and reviewed action; and **recomputes** the seeded mathematical report before binding it. Unknown, duplicated or unselected mathematical results fail closed. MP4s are not modified.

## Interpreting the output

Each clip has either `math_status=no_hypothetical_calculation` or `math_status=conditional_heads_up_all_in_what_if_only`. In the latter case, the result includes the weighted range, model, equity, sampling CI, simplified call EV, sampling EV CI, trials and seed. **The confidence interval covers Monte Carlo sampling only**, not range uncertainty, OCR errors, rake or future betting. The calculations are not verified video EV and cannot establish a mistake. All output authorization flags remain false; clip order remains the human-selected order.

A real recorded session is still required to calibrate visual recognition and measure accuracy against human annotations. No video capture, poker-site integration, real-time assistance, playable table, or automated betting is included.
