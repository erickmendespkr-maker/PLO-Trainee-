# Macro08 — Visual codes and offline ROI reuse
Base 5ad01f0fc33dc6f757c0c1bb0d20da67125be455. PLO5 only, offline post-session. Branch feature/plo5-plo6-training; no main writes. Recovered local subset /mnt/data/plo5_05b, not a full checkout. Prior DNS blocker was not re-tested in this cycle.

## Delivered
- ebf73c42380537b40250fcaffd43f501d69517a1, e2cb68fce785bb00449a84b3933f3fdef379ee0c: plo5_visual_codes.py + 6 tests. Versioned exact pixel codebook; namespace/profile/field/geometry/mode; SHA-256 reporting, actual bytes used as equality key; bounded manually labeled bank, conflict abstention; generic ROI decoder cache; LayoutCache reuses all RGB patches consumed by original mixed_money.detect; MixedReader preserves four-slot observation roster, caches exact grayscale pot/stack patches, validates manual labels via existing parser, retains OCR fallback. Codebook JSON schema {"version":"plo5-exact-visual-v1","rows":[{"profile":...,"field":...,"size":[w,h],"mode":"RGB" or "L","hex":...,"label":...}]}. Generic decoder namespace must distinguish model/version/configuration. No similarity matching of amounts/actions.
- 4dfe72a202bca2079484223d127bee7af2353daa, 0cbe47befdd10486a3265e854b1f9f5c8c79955d: exact two-region card codes and 3 tests; rank patch label is full card, suit patch label separately corroborates suit; no guess from one region. Explicit conflicts abstain. False guard falls back to existing special-geometry recognizer. Labels are unverified manual references, not proof.
- 57f4c8a9406651dccd868c8b074014b994bc8dda, 6b5a390d1c573b0a0f3c31fafb32ad28dc445119: exact action OCR cache and 2 tests; threshold and geometry included, current coordinates re-bound, ROI hash checked, no action/hand certification.
- 7d324f9e5ce13d1bd6503bc9ea37d649c97d398e, 46fd75655a243bf1d962fd0f036c5cd63b117f86, 6c9906840622548d44be1ea346b2724d5ee7cd04, 32cfb49ede4eb26415479003d44f15f88182ecff: opt-in wiring in existing mixed review, card reader, audited action CLI. Existing default reader and special-geometry guards preserved. Bank SHA-256 included/rechecked. These three modified integration files were read and patched against exact remote blobs, and final blobs confirmed remotely, but NOT executed end-to-end locally; the full dependency graph/banks were not recovered. Standalone components tested below. CLI opt-in: python video_analyzer/plo5_mixed_review.py VIDEO.mp4 NEW_OUTPUT --visual-codes [--money-codebook BANK.json] [--card-bank EXISTING_BANK.json --card-codebook CARD_CODES.json]. Action CLI optional --cache-capacity 512. Card code namespaces: pppoker-1504x696-card-v1, suprema-1504x696-v1-card-codes-v1 or existing soft profile + -card-codes-v1; fields hero/rank, hero/suit, board/rank, board/suit.

## Verified local code and tests
Original plo5_mixed_money.py a0e6b7b85f44da9dba6cae48f21776649d0c40c7 and plo5_singleflight.py 3741d0f7b59064909f296c69c55966558f74e9a2 recovered byte-exact from GitHub.
Six new files matched local tested blob hashes:
 eee08579bd4f1f5ac96174e422cbfc0e7eb4c6be plo5_visual_codes.py
 cea5b7c7cb38fce708b3c50718ca2222255309dd test_plo5_visual_codes.py
 322d3cbde8d714a3b191d3fc87bed812eef95e73 plo5_card_codes.py
 662466d91500cf4f15e4a5f93c51d2c0083d04fd test_plo5_card_codes.py
 07c56eb2691b14e85a8e328622608fc2cfd5cfb5 plo5_action_cache.py
 6287fc74f595170499b27b9d56e62bf7fa582760 test_plo5_action_cache.py
Final remote wiring blobs (not local full integration tests):
 55fcbc155535518025c073bd358876656a1dd934 plo5_mixed_review.py
 c77b6bbc1a3b13b4a410e42c02d0e9f16e8445e4 plo5_card_review.py
 18d16d4b47e7f8f8dcff1d7adcd526ac391e8ba6 plo5_action_candidates.py
From recovered video_analyzer directory:
    PYTHONPATH=.. PLO5_CFR_EXE=../native/cli PLO5_MULTISTREET_EXE=../native/multistreet PLO5_MULTIWAY_EXE=../native/multiway PLO5_INDEX_EXE=../native/index_batch PLO5_RANK_EXE=../native/rank_batch PLO5_RANK_CATALOG=../rank_macro07/rank_catalog.json python -W error::ResourceWarning -m unittest discover -q
    Ran 98 tests in 23.325s
    OK
    python -m compileall -q .
    exit 0
87 previous + 11 new methods. Pillow 12.3.0; original detector emitted deprecated getdata warning in an individual test (no failure). No full repository regression.

## Synthetic measurements
300 frames repeating three generated layouts (4,3,1 occupied fixed slots); 1200 layout detections, 1197 cache hits, 3 misses; exact parity to original detector. Baseline 0.468857197 s, cached 0.058004281 s (8.08x). 30 synthetic frames with mocked monetary reader: 160 logical active pot/stack reads, 156 hits, 4 actual mocked calls. Not OCR accuracy or real-video speed. Existing legacy money cache already performs exact reuse.

## Real development video
Fetched only private Poker_Parte_01.mp4 from designated Drive folder (167993622 bytes, SHA-256 c9aad5102a54941b8cb5f4bbc20eca45fc757ff96fd95de173c0ac0d95ac19eb, 1504x696, duration 1618 seconds). No private screenshots/video/label bank committed. Parte 06 reserved and not fetched. Extracted 20 PNG development samples using ffmpeg -nostdin -v error -threads 1 -ss 1450 -i Poker_Parte_01.mp4 -t 20 -vf fps=1 -an -threads:v 1 -y frame_%03d.png. This fps-filter sampling is a benchmark, NOT the existing audited PTS extraction and not an independent holdout. All frames detected four active fixed table slots.
- 80 layout decisions: original 0.030105047 s, cached 0.012976073 s; 55 hits, 25 misses; exact parity. 2.32x stage-only speedup.
- 160 pot/stack candidates, 140 non-null. Compared original mixed-review Reader.scan algorithm reproduced from source (same SingleFlight and original Tesseract read) with MixedReader, no manual bank; 130 hits / 30 misses in both, identical original result fields; 1.700144047 s vs 1.685832813 s, effectively no material total-stage acceleration on this window. One sequential measurement; no accuracy claim.
- Manual bank: first print visually labeled eight displayed pot/stack values; following 19 development prints, 152 active reads, 62 manual-code matches and 90 OCR-fallback source observations; 122 cache hits, 30 misses. 1.520577596 s. Exact match coverage not independent accuracy; repeats can be the same hand.
- Manual card bank: first print visually labeled five hero cards on PPPoker table 1, original regions geometry (rank/suit crops); following 19 prints, 8 exact card candidates of 95 slots, no full five-card exact frame, no conflicts. Shows why existing shape/color classifier fallback remains essential. No accuracy or generalization claims.

## Remaining / next
Macro08 partial. New layout cache supports dynamic visibility only within fixed 1504x696 four-slot geometry; not arbitrary window resizing/rearrangement. Existing seat/dealer/roster classifiers inspected and retained; no new position calibration or independent action sequence validation. Need recover existing calibrated banks, handle highlighted board, train on Parte 01 and independent Parte 06 holdout with reference labels; benchmark actual OCR, decoder and full pipeline, validate CLI wiring, support dynamic geometries, integrate all ROI fields, avoid repeated process pool overhead, review memory and Windows. No C++ visual rewrite: current Pillow/OpenCV paths already native for key operations; benchmark points to OCR/recognition rather than layout arithmetic. Prior solver and database backlogs preserved. Macro09 can proceed on hand reconstruction candidates only; unknown evidence must not become confirmed actions, stacks, positions or financial outcomes. Do not claim 5–10 min/hour target achieved.
