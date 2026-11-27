# Macro15 — Mixed visual banks and all-seat candidate evidence
Base c5a1dc9b895f4474458c56c924ed3e69fa867b5b. PLO5 offline post-session only. Branch feature/plo5-plo6-training. No main writes. Recovered local subset /mnt/data/plo5_05b, not full checkout or Windows certification.

## Delivered
- 4f94a5c5c60573bb3681c87d2945af9172c00993: mixed PPPoker/Suprema card candidate reader using original PPP geometry, feature extraction and thresholds, Suprema v1 geometry, connected glyph component cleanup and highlighted-board abstention, distinct banks/cache keys. Explicit calibration only; no pseudo-labels. Equivalent distance numerator delta=sum(abs(a-b)); denominator max(255,(sum(a)+sum(b)+delta)/2); precomputed reference mass, Pillow native image difference.
- 3cdec37f87b2e4bb1bbe5466e43395e0916dfc9c: six fixed seat stack/action ROIs per platform; Tesseract stack candidates with strict BB parser, confidence >=.75 and border cropping; manually labelled color/glyph action template bank (normalized RGB 36x10, max mean absolute distance .045, runner-up margin .018); no action OCR fallback with bank. Dealer template geometry/glyphs from existing seat_candidates, optional OpenCV. No confirmed dealt-seat roster, position, action amount/order, financial result or count of distinct actions.
- bf35a63409d9e8f2c99f9d1bc88d3432cda253aa: five tests distance identity, invalid banks/geometry, action conflicts/unknown, repeated observation counters and invalid calibration platform.
- 35526cc934aa71a6a8513556b8a2475d05b8d0d8, c816876d54cf6a62a79b1a86b647b610ac2224ff, c27d7286b5321599387d896e21c9b6874168fb46: opt-in CLI and GUI for mixed card banks and detailed seat evidence; source bank hash checked; HTML summary and expandable per-frame seat readings; no auto EV. GUI detailed mode intentionally optional due OCR cost.
- f092c0752cfd5c7ce7b5e546fcd9e2a3632b617b: README with optional OpenCV dependency and mode limits.

Seven published blobs match local files:
4ca287e1e615a174c8b894fd0cb165c3bcbd2a0c plo5_mixed_cards_v2.py
5503273544c1c2f4a8d7af9ca55d1d98f53f414f plo5_seat_evidence.py
cf213c6f0bf4b8c30c46bfb356935d86480a964b test_plo5_mixed_cards_v2.py
19de8c088ebb8dd0badc43ca1538b1321fc8a616 plo5_mvp.py
7a0919ca704bd53b667b7c05a769ed102273af2c plo5_review_session.py
70b737a35927275f88be4df7f69fbacba489c25d plo5_mvp_gui.py
1fd954ce19c2b5f1bfc8ddf6d8674cd5522f9135 packaging/LEIA-ME.txt

## Calibration and evaluation
Local Parte01 training screenshots at requested FFmpeg seek seconds 200,600,1000,1400,1458,1540 and extra Suprema at 800,1200,1300. Extra extracted images 900,1100,1500 not used. Manual labels, feature/suit guards. These seek-based single PNGs do not establish exact source PTS. PPP bank increased 42 ->149 unique masks (+107); Suprema 56 masks; all 13 ranks in each. Action bank 44 PPP +14 Suprema normalized label images, manual labels. Original complete banks still unavailable. Derived templates in private package only, no video, avatar, raw full-frame or private history committed.
Bank SHA-256:
64bba9dedab5806c1125448d93cd0676448fb7dafd7cf861a5be08be169111ca ppp_bank.json
565dcf11220d6f2dfe76f50f966360f2b6b49b16dfeedd78d49fbe34b82fb8af suprema_bank.json
8af0ead07ba8901981a899a5a92bebe05f366b6fe097010dbc9769156aea4c3d action_bank.json
Exploratory evaluation on Parte06 requested seek seconds 200,400,650, visually labelled manually. No bank trained on these frames, but inspected during development and seat ROI iterations; not an untouched blinded holdout or generalizable accuracy. 9 PPP table observations, 1 Suprema.
|field|old correct/unknown/wrong|new correct/unknown/wrong|
|PPP hero (45)|37/8/0|39/6/0|
|PPP board incl empty (45)|30/14/1|37/8/0|
|Suprema hero (5)|not supported|1/4/0|
|Suprema board incl empty (5)|not supported|3/2/0|
PPP complete hero groups 2/9 ->4/9; complete boards 3/9 ->4/9. Suprema 0/1 complete for each. No full hand reconstructed.
60 seat slots: stacks 55 correct visible, 1 unknown visible, 4 blank/unreturned, 0 incorrect candidates; action labels 33 correct visible, 5 unknown visible, 22 blank/unreturned, 0 incorrect candidates; 10/10 dealer marker location. Blank/unreturned does not prove empty seat or absence of action. Labels may persist across frames; never count as unique actions. No stack or payout truth for complete session.
Same expanded PPP bank, 3 images, cache disabled, old vs new sequential trials: old 0.531369,0.490096,0.506340s; new 0.188052,0.202369,0.192280s. All slot dictionaries and grouped cards equal. Median 2.633x faster. This isolates card recognition only, not OCR, Suprema or entire session.

## Actual integration runs
CLI: python video_analyzer/plo5_mvp.py video INPUT.mp4 NEW_OUTPUT --start N --seconds 10 --ppp-card-bank calibration/ppp_bank.json --suprema-card-bank calibration/suprema_bank.json --action-bank calibration/action_bank.json
Existing source SHA256 and exact RGB/PTS checks retained for source and selective second pass.
|source|window|frames|card segments|display changes|stack candidates|label candidates|dealer candidates|6-stack observations|PNG count|wall s|RSS KiB|
|01|1000-1010|10|5|5|199|150|40|10|7|10.44|156420|
|06|200-210|10|2|6|199|84|39|20|8|9.81|154312|
240 seat observations each, 40 table observations each. Card cache hits/misses 313/87 and 280/110; seat cache 315/165 and 305/175. Counts not verified hand histories. One timed run each, no full-session throughput target met; detailed mode is expensive. Both reports generated locally, private.
Recovered suite 155 tests in 26.885s OK, all previous native env vars as Macro14, compileall and Linux xvfb GUI smoke passed. 150 prior +5 new methods. Pillow deprecation warning getdata on individual run, no failure.

## Package
PLO_Trainee_Macro15_Candidato_Fontes.zip 263517 bytes, 118 entries, SHA256 c6c9d4f922e760109860d98a33b7deefcc8d6581c63b231df6a9d0805b3914ad. Derived from Macro14 file roster +3 new Python modules/tests and 2 banks. ZIP integrity, clean extraction and 117 hashes verified; preflight and GUI open/close Linux passed. No Windows executables or installer; optional opencv-python-headless for dealer. Prior DNS issue not retested. No actual DriveHUD export, no Windows validation.

## Release gates
Macro15 partial. Need wider independent Suprema calibration and highlighted/showdown geometry, explicit dealt-roster and seat identity tracking, amount paid and call-to/raise-to reconstruction with denser sampling, reliable full hand boundaries and actual pot payout/auto-rebuy reconciliation. Connect only sufficiently supported complete snapshots to existing legal action recovery/ledger; don't invent unknown contributions, infer actual winnings from stack changes, or mark candidates confirmed. Keep prior backlogs, actual DriveHUD import, model range provenance, session benchmark on target hardware and Windows packaging. No verified complete real-video hand, no full MVP or GTO certification.
