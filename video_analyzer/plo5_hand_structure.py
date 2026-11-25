"""Descriptive preflop PLO5 features; no strategic frequencies or EV inferred."""
from collections import Counter, defaultdict
from itertools import combinations
from math import comb

if __package__:
    from .plo5_hand_classes import classify, RANKS, SUITS
else:
    from plo5_hand_classes import classify, RANKS, SUITS

VALUES = {r:14-i for i,r in enumerate(RANKS)}
WINDOWS = [(5,frozenset('A2345'))]+[(high,frozenset(RANKS[14-high:19-high])) for high in range(6,15)]


def describe(cards):
    """Structural features and straight/flush potential, not a hand-strength score."""
    identity=classify(cards)
    h=sorted(cards,key=lambda c:(-VALUES[c[0]],c[1]))
    ranks=Counter(c[0] for c in h)
    groups={s:[c for c in h if c[1]==s] for s in SUITS}
    pairs=[]; straight_patterns=defaultdict(int); nut_patterns=[]
    for a,b in combinations(h,2):
        rr=frozenset((a[0],b[0])); windows=[]
        if len(rr)==2:
            for high,window in WINDOWS:
                if rr<=window:
                    need=tuple(sorted(window-rr,key=RANKS.index))
                    windows.append({'high':high,'board_ranks':list(need)})
                    straight_patterns[need]=max(straight_patterns[need],high)
        pairs.append({'cards':[a,b],'paired':a[0]==b[0],'suited':a[1]==b[1],
                      'straight_windows':windows})
    # Compare straight heights only, not overall nuts (flushes etc. may win).
    # Required opposing private ranks are outside the three board ranks.
    for triple,hero_high in sorted(straight_patterns.items(),key=lambda x:tuple(RANKS.index(r) for r in x[0])):
        tr=frozenset(triple)
        opp_high=max((high for high,w in WINDOWS if tr<=w and all(ranks[r]<4 for r in w-tr)),default=0)
        if hero_high>=opp_high:
            nut_patterns.append({'board_ranks':list(triple),'hero_straight_high':hero_high,
                                 'max_opponent_straight_high':opp_high})
    suits=[]
    for s,g in groups.items():
        if len(g)<2: continue
        top=g[0][0]
        suits.append({'suit':s,'cards':g,'suited_pairs':comb(len(g),2),
                      'ace_high_pair_available':top=='A',
                      'higher_unseen_ranks_than_top':[r for r in RANKS[:RANKS.index(top)] if r+s not in h],
                      'unseen_suit_cards':13-len(g),'three_same_suit_flops':comb(13-len(g),3)})
    blockers=[{'rank':r,'held':ranks[r],'unseen':4-ranks[r],
               'opponent_two_card_rank_pairs_remaining':comb(4-ranks[r],2),
               'opponent_two_card_rank_pairs_removed':6-comb(4-ranks[r],2)} for r in RANKS if ranks[r]]
    distinct=[r for r in RANKS if ranks[r]]
    counts=sorted(ranks.values(),reverse=True)
    return {'variant':5,'status':'DESCRIPTIVE_PREFLOP_STRUCTURE','hand_class':identity,
            'rank_groups':[{'rank':r,'count':ranks[r]} for r in distinct],
            'rank_partition':counts,'paired_private_combinations':sum(comb(n,2) for n in counts),
            'distinct_ranks':len(distinct),'broadway_cards':sum(ranks[r] for r in 'AKQJT'),
            'rank_span_ace_high':VALUES[distinct[0]]-VALUES[distinct[-1]],
            'adjacent_rank_gaps':[VALUES[a]-VALUES[b]-1 for a,b in zip(distinct,distinct[1:])],
            'private_pairs':pairs,'straight_capable_pairs':sum(bool(p['straight_windows']) for p in pairs),
            'distinct_straight_flop_rank_patterns':len(straight_patterns),
            'top_straight_flop_rank_patterns':nut_patterns,
            'suited_groups':suits,'rank_blockers':blockers,'held_card_blockers':h,
            'flop_denominator_hero_only':comb(47,3),
            'interpretation_pt':[
                f'{len(distinct)} ranks distintos; {sum(comb(n,2) for n in counts)} pares privados de mesmo rank entre 10 combinações.',
                f'{sum(bool(p["straight_windows"]) for p in pairs)} pares privados distintos podem completar uma sequência com três ranks do board, incluindo o ás baixo quando aplicável.',
                f'{len(suits)} naipe(s) com pelo menos duas cartas privadas; {sum(x["ace_high_pair_available"] for x in suits)} com ás e outra carta do naipe.',
                'Os blockers reduzem combinações físicas disponíveis; não determinam o range adversário.',
                'Potencial de sequência mais alta e flush com ás não comprova nuts absolutos, equity ou decisão correta.'],
            'scope':'preflop_hero_only_rank_and_suit_combinatorics','frequency':None,'ev_bb':None,
            'equity':None,'gto_solution':False,'video_verified':False}
