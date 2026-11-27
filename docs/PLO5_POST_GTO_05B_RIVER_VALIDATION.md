# POST-GTO 05B — partial validation, 2026-11-27

Offline PLO5 only. Source commit 45618eff08b9b7453dd30c6ea5c420a6399ce16c. Branch feature/plo5-plo6-training. Direct git ls-remote failed (DNS could not resolve github.com, exit 128); seven files fetched through authorized connector and transferred to Linux, each verified by git hash-object against returned blob SHA:

| Module | Blob SHA |
|---|---|
| offline_omaha_showdown.py | c1ebc5025bf9305d451576721d2721bfae4e6dfa |
| plo5_evaluator.py | 21cf0f3ba842994f74a8fc55383462b1a80cc07b |
| plo5_post_gto_context.py | 378c517b53e29e244cb752829128a6de47c865cc |
| plo5_post_gto_river.py | 725fa6d1bbd34df5ee42de0509c3f322dbe3f9ba |
| plo5_post_gto_tree.py | 72857143ff1d71009a210fee99b6d3aa1dac43a1 |
| plo5_pre_gto_context.py | d9e53867ace6f77ee8c5fc782b86e1f87d4bc194 |
| plo5_rank_cache.py | 8836846722c40dd1bea3d05cc199b23159097d68 |

Python 3.13.5, x86_64 Linux. In recovered video_analyzer directory: python -m compileall -q .; python plo5_pre_gto_context.py; python plo5_post_gto_context.py; python plo5_post_gto_tree.py all exit 0. New test file blob 1053b8737c14a8a33a1efeed934efb82c0363c1b, committed at b6d4a46631cb5e35a3f1f33f7815f3b0ab76397b. python -m unittest -v test_plo5_post_gto_river exit 0:

    test_asymmetric_stack_and_short_raise ... ok
    test_blockers_and_budgets ... ok
    test_known_winner_and_loser ... ok
    test_polar_oracle ... ok
    test_tie ... ok
    Ran 5 tests in 0.137s
    OK

Initial tie assertion expecting seven-decimal equality failed: 1.0000495000490148 vs exact game value 1; this is finite-iteration approximation, not demonstrated solver defect. Updated regression checks exact value bracketed by independently motivated best-response bounds, with .001 tolerance. Tie gap .000148514851485 BB.

Polar fixture: 2 BB starting pot, 2 BB stacks, one bet size, 9 nodes, two legal deals, 16 pure plans seat0 and 4 seat1. Explicit payoff formula independent of production evaluator, tree and BR recursion. Value and both BR bounds agree within nine decimal places at all five iteration counts.

| Iterations | Gap BB | Value BB | Seconds |
|---:|---:|---:|---:|
|50|0.0857890026238|0.998669925313|0.001346|
|100|0.0537295100495|1.00047763367|0.002038|
|500|0.0232119885701|1.00020076012|0.008037|
|1000|0.0115153907368|1.00006958296|0.016248|
|5000|0.00548239981927|0.999979395472|0.074655|

Final gap/pot 0.2741199909635%, meets provisional 0.5% target for this fixture only. No full checkout, full regression, C++ parity, Windows, holdout, broad ranges, per-action EV oracle, multiway/rake, or video integration tested. No changes to solver code. Next: native protocol and kernel parity, expanded independent fixtures, complete 05B before 05C/turn; preserve all video and preflop backlogs. No claim of profitable strategy or full GTO solution.
