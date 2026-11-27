"""Exact HU public flop marginal after a modeled preflop action path.
No strategic continuation or inference of actual opponent cards is performed.
"""
from collections import defaultdict
from fractions import Fraction
from itertools import combinations
from math import comb
from plo5_pre_post_bridge import _condition, _ratio
from plo5_post_gto_context import DECK
from plo5_pre_gto_context import need

VERSION = 'hu-pre-flop-chance-v1'


def distribution(context, likelihoods, *, max_outcomes=1000000):
    need(type(max_outcomes) is int and 1<=max_outcomes<=10000000,'Invalid chance budget')
    c,state,pairs,history_probability,_=_condition(context,likelihoods)
    per_pair=comb(42,3)
    outcomes=per_pair*len(pairs)
    need(outcomes<=max_outcomes,'Flop chance budget exceeded')
    mass=sum(w for _,w in pairs)
    # Aggregate by public board only, retaining no dense pair-by-board table.
    boards=defaultdict(Fraction)
    for (a,b),w in pairs:
        remaining=sorted(DECK-set(a)-set(b))
        need(len(remaining)==42,'Invalid remaining deck')
        for flop in combinations(remaining,3):boards[flop]+=w
    total=mass*per_pair
    need(sum(boards.values())==total,'Chance mass mismatch')
    return dict(version=VERSION,variant=5,legal_pairs=len(pairs),outcomes=outcomes,
                public_boards=len(boards),history_probability=_ratio(history_probability),
                branches=[dict(flop=list(f),probability=_ratio(w/total)) for f,w in sorted(boards.items())],
                continuation_solved=False,gto_solution=False)
