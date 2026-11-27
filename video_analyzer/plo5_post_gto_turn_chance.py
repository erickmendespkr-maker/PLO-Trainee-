"""Exact physical HU chance from turn to river, not a strategic turn solver."""
from collections import defaultdict
from fractions import Fraction
from plo5_post_gto_context import normalize, DECK, identity
from plo5_pre_gto_context import need


def distribution(context, max_outcomes=155648):
    c=normalize(context)
    need(len(c['board'])==4 and len(c['seats'])==2,'HU turn only')
    need(type(max_outcomes) is int and 1<=max_outcomes<=155648,'Invalid chance budget')
    a,b=[c['ranges'][p] for p in c['seats']]
    need(len(a)*len(b)<=4096,'Pair budget exceeded')
    board=set(c['board']); pairs=[]; total=0
    for x in a:
        for y in b:
            h,k=tuple(x['cards']),tuple(y['cards'])
            if set(h)&set(k):continue
            weight=x['weight']*y['weight']; total+=weight
            pairs.append((h,k,weight))
    need(total>0,'No legal joint deals')
    need(len(pairs)*38<=max_outcomes,'Chance budget exceeded')
    by_card=defaultdict(list); masses=defaultdict(int)
    for h,k,w in pairs:
        possible=DECK-board-set(h)-set(k)
        need(len(possible)==38,'Invalid remaining deck')
        for card in sorted(possible):
            by_card[card].append((h,k,w));masses[card]+=w
    def ratio(n,d):
        f=Fraction(n,d);return [f.numerator,f.denominator]
    # P(card) and P(deal|card) are distinct. Never expose card at a turn infoset.
    return dict(variant=5,context_key=identity(context),legal_pairs=len(pairs),outcomes=len(pairs)*38,
                branches=[dict(card=card,probability=ratio(masses[card],total*38),
                    joint_deals=[dict(holdings=[list(h),list(k)],probability=ratio(w,masses[card]))
                                 for h,k,w in by_card[card]]) for card in sorted(by_card)],
                root_prior_only=True,action_reach_modeled=False,gto_solution=False)
