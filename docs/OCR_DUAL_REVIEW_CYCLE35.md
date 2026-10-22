# OCR blind dual-review gate (cycle 35)

Scope: recorded, offline PLO5/PLO6 only. This document specifies the locally tested `ocr_label_consensus.py` module; the module is **not** considered published until separately committed.

1. Two annotators label the same SHA-256-bound, decoded-PTS image template without seeing OCR predictions.
2. Validate each export against the original evidence manifest and each PNG digest.
3. Accept a sample into the reconciled benchmark template only when both human-entered values match exactly.
4. Any conflict, one-sided label, or missing label stays `unlabeled` and enters the manual adjudication queue.
5. Agreement is not ground truth or OCR accuracy; identities and independence of annotators are not authenticated.
6. Only after adjudication, compare reconciled human labels against OCR candidates using the separate benchmark module. Never infer hidden cards.

Synthetic demonstration: 8 tasks, 3 doubly labeled, 2 matching, 6 pending review (including 1 conflict). The synthetic values are not authentic poker observations.

No main, production, live poker integration, credentials, or spending changes.
