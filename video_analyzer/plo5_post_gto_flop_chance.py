"""Macro04 foundation: bounded streaming ordered flop runouts for HU PLO5."""
from fractions import Fraction
from itertools import permutations
from plo5_post_gto_context import normalize, DECK
from plo5_pre_gto_context import need


def ordered_runouts(context, max_pairs=256, max_outcomes=379392):
    """Yield (holding0, holding1, turn, river, exact prior mass).

    Hidden runouts are not a player information set. Betting reach is not
    included here. The caller must reveal cards only at public chance nodes.
    """
    c=normalize(context)
    need(len(c['board'])==3 and len(c['seats'])==2,'HU flop only')
    need(type(max_pairs) is int and 1<=max_pairs<=4096,'Invalid pair budget')
    need(type(max_outcomes) is int and 1<=max_outcomes<=6070272,'Invalid outcome budget')
    a,b=[c['ranges'][p] for p in c['seats']]
    need(len(a)*len(b)<=max_pairs,'Pair budget exceeded')
    pairs=[(tuple(x['cards']),tuple(y['cards']),x['weight']*y['weight'])
           for x in a for y in b if not set(x['cards'])&set(y['cards'])]
    mass=sum(w for h,k,w in pairs);need(mass>0,'No legal joint deals')
    need(len(pairs)*1482<=max_outcomes,'Outcome budget exceeded')
    board=set(c['board'])
    for h,k,w in pairs:
        remaining=sorted(DECK-board-set(h)-set(k));need(len(remaining)==39,'Invalid remaining deck')
        probability=Fraction(w,mass*1482)
        for turn,river in permutations(remaining,2):yield h,k,turn,river,probability
