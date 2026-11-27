# PRE-GTO 33 — Executed restricted HU experiment
Linux standalone harness, native protocol and kernel Git blob hashes respectively ffe2ce20d6d30b5def04ba9bc8df821022d08a4b and 02ff6a05c27a43295d9bb48ef14367794efae0bc. Compiled C++17 -O3 -Wall -Wextra -Werror.
Synthetic 2 BB effective HU context, blinds 1/2 chips, zero rake, showdown-only continuation. Equal-weight explicit holdings; no video evidence.
SB: As Ah Ks Qh Jd; 8s 7s 6h 5h 4d.
BB: Ac Ad Kc Qd Jh; 9c 8c 7d 6d 5s.
Independent Python five-card ranking with exact 2+3 enumeration, 2000 uniformly sampled boards per pair, seed 42+2*i+j.
SB equity matrix: [[0.5105,0.542],[0.467,0.383]].
Wins matrix: [[374,1084],[934,618]]. Ties: [[1294,0],[0,296]].
CFR+ 2000 iterations, ten public nodes, eight information sets, 18 action rows.
SB value -0.09749986798274586 BB; independent exhaustive pure best-response bounds [-0.09750014222055636,-0.09749972576211892] BB; gap 4.1645843744386735e-7 BB.
Measured equity 1.693898654 s; native subprocess training 0.007321072 s.
Standalone JSON and SQLite experimental artifacts created locally; SQLite integrity_check returned ok. Not the production database schema or an integrated repository test.
The gap is conditional on the sampled equity matrix and restricted game, not an estimate of full-game exploitability. Monte Carlo uncertainty, generalization to 100 BB, multiway ranges and future betting remain unresolved. No full PLO5 GTO claim.
