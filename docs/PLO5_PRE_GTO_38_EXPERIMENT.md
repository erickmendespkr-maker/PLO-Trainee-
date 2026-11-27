# PRE-GTO 38 — Executed 100 BB experiment
Standalone Linux harness, reconstructed betting tree, native CFR executable from PRE-GTO 35F. Reused the four sampled equities from PRE-GTO 33; no new equity simulations.
HU, 100 BB effective, SB=1 BB=2 chips, zero rake, pot-only raises, two explicit physical holdings per seat, showdown-only continuation.
5000 iterations, 34 public nodes (12 decision, 11 fold terminal, 9 flop transition, 2 all-in showdown), 24 information sets.
Native subprocess training elapsed 0.015596999 s. Policy normalization checked. Independent Python recursive best response bounds: [-0.03657732761332366,-0.03653973895316534] BB; policy value -0.03655841935683849 BB; gap 0.00003758866015832196 BB.
This is conditional on sampled equity and the restricted game, not real-game exploitability or a full GTO solution. No multiway coverage, no authentic hand history, no modeled future betting, no official integrated generator execution. The JSON summary was produced locally; production database not updated in this cycle.
