# Cycle 240 — audited offline session + table-crop cross-index

## Scope
Only recorded PLO5/PLO6 sessions; no live poker integration, playable tables, AI opponents, betting, or automatic promotion of OCR into mathematical facts. Follow `docs/VIDEO_ANALYZER_SCOPE.md`.

## Added
- `offline_ev_session_crops.py`: read-only HTML cross-index joining an existing conditional-EV batch directory with its manually cropped MP4 directory.
- `test_offline_ev_session_crops.py`: 26 self-contained synthetic tests. A single FFmpeg fixture generates four colored quadrants, a source batch and four crops, without checking in video binaries.
- HTML places full-frame and per-table MP4 players side by side, with per-clip JSON evidence links, source timestamps, hand IDs, table IDs and explicit unverified-assumptions warning.
- Source and crop ledgers are cross-checked by SHA-256; every clip's video hash, report hash, source video, clip identity, table, hand, timestamp, ROI and no-OCR-authorization flag must agree. Rejected inputs do not create an index.
- HTML escapes user-visible strings and percent-encodes relative links; existing outputs are never overwritten. No modification of MP4 files.

## Run
```bash
python video_analyzer/offline_ev_session_crops.py batch_output crop_output
python -m unittest -v video_analyzer/test_offline_ev_session_crops.py
```
The second command assumes Python can import modules from `video_analyzer`, as in the other standalone tests; from the repository root, this alternative is explicit:
```bash
cd video_analyzer
python -m unittest -v test_offline_ev_session_crops
```

## Verification on Linux
- 26/26 new synthetic tests passed.
- 285/285 selected tests passed across Monte Carlo input, equity, EV, individual and batch clip export, original and crop overview, crop pixel checks and new cross-index.
- The new test suite synthesizes four MP4 table crops using FFmpeg/FFprobe. It verifies eight HTML video links and rejects tampered hashes, timestamps, geometry, duplicate IDs, unsafe filenames, symlinks, JSON duplicate keys, non-finite values and output collisions.
- Source and test Git blob SHAs were checked against the local files after publishing.
- **Not** the full repository test suite, a Windows test or a real poker-session test.

## Limitations
- The cross-index requires already-rendered full-frame and cropped batches and complete one-to-one clip coverage; it does not automatically identify tables, detect hands, OCR cards, infer ranges or compute new EV.
- The table regions remain manually declared. The 95% Monte Carlo intervals elsewhere in the project do not cover OCR/range/model uncertainty.
- An authorized annotated 3–5 minute recording is still missing for visual accuracy measurements; 40–60 minute throughput and Windows remain unverified.
- Next: reviewable table-region proposals and per-street evidence, with strict human confirmation before mathematical use.
