# PLO Trainee — Cycle 47: offline review draft binding

Scope: recorded PLO5/PLO6 video analysis only, as defined in `docs/VIDEO_ANALYZER_SCOPE.md`. No live play, betting integrations, or production changes.

The new `video_analyzer/activity_review_draft_binding.py` checks a manually edited review draft against its original queue-derived template. It rejects modified queue SHA-256, recording identity, table/hand/event/timestamp identities, reordered decisions, extra keys, and any attempt to change the protected equity/EV-blocking flags. It **does not** authenticate frame bytes or permit equity/EV.

Tests: `python -m unittest -v test_activity_review_draft_binding` (6 local tests passed). The full local cycle-47 package also contains an interactive offline HTML editor and a typed draft validator (14 more tests); those larger files are not yet synchronized to this branch. The local full suite passed 604 tests. Remote CI has not been verified.

A consented 3–5 minute PLO5/PLO6 recording remains necessary to calibrate OCR and hand reconstruction. Do not promote draft annotations to mathematical analysis without a separate evidence audit and explicit scenario/range assumptions.
