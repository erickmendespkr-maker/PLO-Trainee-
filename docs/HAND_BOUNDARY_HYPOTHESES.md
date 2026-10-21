# Video analyzer — hand-boundary hypotheses

This module is intended for offline review of recorded PLO5/PLO6 sessions.
A change of visible private cards or a non-continuing board may suggest that a new hand began, but neither is proof. Each candidate must remain unverified until a human checks the recording. Different tables must be processed independently. Do not send raw OCR hypotheses to equity or EV calculations.

Validation plan: test board progression, board resets, private-card changes, cross-table isolation, conflicting timestamps, long gaps and invalid card notation.
