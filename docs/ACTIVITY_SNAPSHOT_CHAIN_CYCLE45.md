# Cycle 45 — Offline reviewed OCR → decision hints

Scope: `docs/VIDEO_ANALYZER_SCOPE.md` remains authoritative. No playable tables, AI opponents, real-time integration, betting or production changes.

Local implementation: `video_analyzer/activity_snapshot_chain.py` links human-reviewed OCR observations to conservative decision snapshots. It verifies table/hand/timestamp identity, source PTS, reviewed values, candidate uniqueness and optional SHA-256 pinning. Only strictly earlier observations may become review hints; no EV is authorized.

Local synthetic validation: **573 tests passed** (20 new), using a four-table fixture with 16 annotated observations and four unverified decision hints. No real session video was used, and this is **not** an OCR accuracy benchmark.

Remote synchronization of the implementation and its dependency `decision_snapshot.py` must be confirmed separately. Do not claim GitHub CI passed based on local tests.

Blocking input: authorized 3–5-minute PLO5/PLO6 recording and ground-truth annotations.