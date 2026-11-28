# Block 38 — exact low-contrast cache equivalence

Both built-in seat OCR paths return the same empty candidate when cropped grayscale contrast is below 15. Collapse these keys only on the existing effective-gray opt-in path; action template and custom decoder paths remain unchanged.

Local isolated tests: 6 passed. Existing real ROI benchmark on three 20-second windows, 59 frames, 2832 ROIs: 752 effective misses versus historical 754 with previous key and 814 raw keys. 150 nonblank preprocessing equivalence checks and 12 actual TSV parity pairs passed. This is an LRU simulation, not full pipeline throughput; low contrast already skips OCR. No accuracy or complete hand certification. Full checkout blocked by DNS; calibration banks, integration regression, native build, terminal bridge and independent validation remain pending. No private evidence published.
