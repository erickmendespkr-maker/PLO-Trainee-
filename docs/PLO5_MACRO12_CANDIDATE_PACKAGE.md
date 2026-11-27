# Macro12 — Offline candidate package
Base 7c621ce22aec5fa043f5942f2792f20d8eca9fdc. PLO5 only, post-session offline. Branch feature/plo5-plo6-training only, no main writes. Direct git ls-remote failed DNS again; recovered local subset /mnt/data/plo5_05b, not full checkout.

## Delivered
- fd4955d68c5647d652a7c4a1e5d858382e8066db: plo5_mvp.py. Candidate entry points check/video/models/history. Video mode scans bounded 2–120s windows in RGB with existing recognition and evidence collector. Second pass only saves PNGs for before/after changes, compares every RGB SHA-256, exact PTS roster, source hash and selected PNG hashes. Reuses observations, no second OCR. Stages report and manifest in temp directory, no intentional overwrite; nonselected sample IDs remain logical .rgb IDs. Existing visual_session produces expandable table crops, not verified hands or EV. Models mode uses existing strategy cache and optional C++ multiway and persistent rank worker.
- dba18cf80411a64c8e4d1e17f88bfbd3ae5a1f69, 43cc32e6029909a7a71181b1d4b8586e691a208b: bounded TXT intake for explicit PokerStars Hand header with 5 Card Omaha Pot Limit / Omaha 5 Cards Pot Limit, one five-card hero deal, summary marker, deduplication; unsupported/incomplete records rejected. Escaped raw text report, no action reconciliation or EV. DriveHUD official help confirms original/plain text and third-party export options (https://drivehud.com/dh2-knowledge-base/how-do-i-export-my-hand-histories/). No actual PPPoker/Suprema DriveHUD export supplied or tested; no DriveHUD database access or claim of complete parser.
- 6f25e18100623ec79a03e69ac935432dce75d98f: three new integration tests (selective evidence, RGB mismatch, declared model). Two history tests also passed.
- 265d402b4021045fff353609e02a6ff7f4e20226: lightweight separate Tk candidate GUI, 3 modes, file paths, time window, environment checks, subprocess logs, local HTML open; automatically uses native binaries when present. Smoke open/close only, not manual GUI end-to-end. Existing old launcher untouched.
- Windows preparation scripts, requirements, readme and two synthetic examples published in packaging/ and examples/. No Windows executables or self-contained installer; Python 3.11+, Tk, FFmpeg/ffprobe, Tesseract must be installed; g++ C++17 optional for accelerated backend. pip may need network to install Pillow; runtime uses local sources. No system-wide configuration changes. Windows script syntax/runtime not executed on Windows.

## Verification
12 new code/script/example blobs matched local hashes:
 ff803f816b6dcf168fe3b43c9dbb96dae00638fc video_analyzer/plo5_mvp.py
 755e836d3ed4d6586c4d1cc35542b8ff6711d5d5 video_analyzer/test_plo5_mvp.py
 1ff928946bb00f7a5a93ffea98e7db7ef39fdac4 video_analyzer/plo5_history_intake.py
 121742c2be9274b8e08c395a874a70606c3f1b0c video_analyzer/test_plo5_history_intake.py
 90477aa9a9ac9924d1520cb22fe0ed41fd059e17 video_analyzer/plo5_mvp_gui.py
 a8612f1b037b356adf61299a44c990429128b3e6 packaging/Abrir_PLO_Trainee.bat
 674118bc819dbb1085f85ae9bfe1facc183aeb4d packaging/Build_Nativo.bat
 9b7ff482a39b4792c0d504399c8006c089f1d3a7 packaging/Instalar_Windows.bat
 08fd8c5d65a3751d58336e68fdb6ac7a6392be62 packaging/LEIA-ME.txt
 7df936ba3982a40d81411fb2e472a296b6c2a38c packaging/requirements.txt
 48ebdedbbcf3c75abcb5519dd80cb1d29afd46d4 examples/history.txt
 4cee3d3658929bd6bce3302fa87becb4d7f18491 examples/models.json
Recovered video_analyzer:
 PYTHONPATH=.. PLO5_CFR_EXE=../native/cli PLO5_MULTISTREET_EXE=../native/multistreet PLO5_MULTIWAY_EXE=../native/multiway PLO5_INDEX_EXE=../native/index_batch PLO5_RANK_EXE=../native/rank_batch PLO5_RANK_CATALOG=../rank_macro07/rank_catalog.json PLO5_RANK_WORKER_EXE=../native/rank_worker python -W error::ResourceWarning -m unittest discover -q
 Ran 139 tests in 27.358s
 OK
5 new methods; compileall passed. xvfb-run -a python plo5_mvp_gui.py --smoke passed. Python 3.13.5 Linux. No full repo regression or Windows validation.

## Package
PLO_Trainee_Macro12_Candidato_Fontes.zip, 176818 bytes, SHA256 dd1e5b4bd10e8ab37fd5cc2617e7e72937b36ee5aee05597b97763efa349f235. 102 entries (101 files plus SHA256SUMS); ZIP integrity check passed; extracted to clean folder and verified 101 file hashes. Rebuilt multiway and rank_worker using g++ -O3 -std=c++17 -Wall -Wextra -Werror. Executed model example (2 decisions, 1 cache hit), text example (1 candidate), GUI open/close, and actual video Parte06 window from extracted package. No Linux/Windows binaries, private video, private screenshots or private policy banks in ZIP. Includes original 300000 synthetic rank-index fixture values from Macro07, not complete database. ZIP available to user locally, not uploaded as release.

## Actual videos
Parte01 [1510,1530) and Parte06 [600,620), real original source MP4s. Full new video mode, with selective second-pass PNG and HTML generation:
|video|frames|changes|PNGs|wall s|peak RSS KiB|
|01|20|9|9|7.73|140516|
|06|20|4|7|5.20|121880|
All 40 PTS, RGB hashes and observation dictionaries matched Macro11 manifests. Extracted-package Parte06 run 5.56s, 127240 KiB, 4 changes/7 PNGs, all 20 PTS/RGB/observations equal. Single measurement per run, RSS from GNU time not aggregate simultaneous RAM, not target Windows hardware. No independently labeled accuracy or completed real hand. Private reports not committed. 16 rather than 40 PNGs, 60% reduction in intermediate count; second pass incurs decoding, not proof of speed gain over all-PNG pipeline. Session goal 5–10 min/hour still unverified.

## Remaining
Macro12 partial: prioritize actual automatic reconstruction of real PLO5 hands and complete all-seat observations, calibrated card/seat/action banks, arbitrary layout, terminal payout/rebuy and room rules, a real DriveHUD export parser and verified hand-to-strategy adapter, deeper range/sizing tests, full repository regression, long-session benchmarking, Windows build/runtime and installer. Preserve Macro01–11 backlogs. Next cycle should target these release gates; do not label package finished or certify GTO. The user needs to supply a real DriveHUD raw/third-party export and Windows test only if those cannot be obtained from already available sources.
