# PLO Trainee — cycle 37: offline OCR error triage

Scope: recorded PLO5/PLO6 video only. No live poker connection, gameplay, or automatic betting.

The local proof of concept adds `video_analyzer/ocr_error_triage.py` and `test_ocr_error_triage.py`. It takes the evidence directory, a human-labeled OCR benchmark template, and an unverified OCR candidate report. It first validates all source PNG SHA-256 hashes and decoded PTS via the existing benchmark, then builds a deterministic, bounded queue of incorrect, ambiguous, abstained, or missing OCR predictions. Pending labels are excluded. Results are **not** inputs to hand reconstruction, equity or EV.

Local synthetic checks: 471 pytest tests passed (387 subtests); 7 tests are new. Existing cycle-36 sample yielded 3 review items (1 abstention, 2 missing), 3 self-reported labels, and 5 pending labels. This is not a measurement of real-world OCR accuracy.

This document is informational. Code and tests are in the local cycle-37 package, **not verified as synchronized to GitHub**. Attempts to publish the existing Wilson confidence-interval module through the connector were blocked. Do not treat documentation publication as code publication.

Blocking validation: an authorized 3–5 minute PLO5/PLO6 video and independent human annotations. No costs or credentials required.
