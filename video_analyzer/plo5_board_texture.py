"""Offline PLO5 board texture, current nuts and explicit heads-up range comparison."""
from collections import Counter
from fractions import Fraction
from itertools import combinations, accumulate
from bisect import bisect_right
from math import comb, log, sqrt
import random

if __package__:
    from .offline_omaha_showdown import _cards, RANKS, SUITS
    from .plo5_evaluator import evaluate, CATEGORIES
    from .plo5_rank_cache import fast_five as _five
else:
    from offline_omaha_showdown import _cards, RANKS, SUITS
    from plo5_evaluator import evaluate, CATEGORIES
    from plo5_rank_cache import fast_five as _five

DECK = tuple(r+s for r in RANKS for s in SUITS)


def board_cards(board):
    if not isinstance(board, (tuple, list)) or len(board) not in (3, 4, 5):
        raise ValueError('Expected flop, turn or river')
    return _cards(board, len(board))


def pair_ranks(board, excluded=()):
    """Each available pair extends to a legal five-card holding on this board."""
    blocked = set(board) | set(excluded)
    triples = tuple(combinations(board, 3))
    return {pair: max(_five(pair + triple) for triple in triples)
            for pair in combinations((c for c in DECK if c not in blocked), 2)}


def texture(board, hero=None):
    b = board_cards(board)
    ranks = Counter(c[0] for c in b); suits = Counter(c[1] for c in b)
    pairs = pair_ranks(b); nuts = max(pairs.values())
    nut_pairs = [list(p) for p,r in pairs.items() if r == nuts]
    # Count pair ranks whose best made hand is a straight or straight flush.
    # For connectivity, separately check whether ANY legal triple forms a straight.
    windows = [set('A2345')] + [set(RANKS[i:i+5]) for i in range(9)]
    triples = {frozenset(c[0] for c in t) for t in combinations(b,3)}
    connected = [sorted(t) for t in triples if len(t)==3 and any(t <= w for w in windows)]
    partition = sorted(ranks.values(), reverse=True)
    suited = sorted(suits.values(), reverse=True)
    result = {'variant':5, 'street':{3:'flop',4:'turn',5:'river'}[len(b)],
              'board':list(b), 'rank_partition':partition, 'suit_partition':suited,
              'paired':max(partition)>1, 'flush_possible_now':max(suited)>=3,
              'straight_possible_now':bool(connected), 'straight_compatible_board_rank_triples':sorted(connected),
              'flop_suit_texture':('monotone' if suited==[3] else 'two_tone' if suited==[2,1] else 'rainbow') if len(b)==3 else None,
              'dry_flop_heuristic':len(b)==3 and partition==[1,1,1] and suited==[1,1,1] and not connected,
              'board_nut_rank':list(nuts), 'board_nut_category':CATEGORIES[nuts[0]],
              'board_nut_pairs':nut_pairs, 'board_pairs_examined':len(pairs),
              'hero':None, 'gto_solution':False, 'video_verified':False}
    if hero is not None:
        h = _cards(hero,5); made = evaluate(h,b); rank = made['rank']
        opponent = {p:r for p,r in pairs.items() if not set(p).intersection(h)}
        ceiling = max(opponent.values())
        result['hero'] = {'made_hand':made,'has_board_nuts':rank==nuts,
                          'cannot_be_beaten_now':rank>=ceiling,'cannot_be_tied_now':rank>ceiling,
                          'opponent_max_rank_after_blockers':list(ceiling),
                          'opponent_pairs_examined':len(opponent),
                          'opponent_pairs_beating_hero':sum(r>rank for r in opponent.values()),
                          'opponent_pairs_tying_hero':sum(r==rank for r in opponent.values())}
    result['scope']='current_made_hands_only_not_future_runouts'
    return result


def _range(entries, board):
    if type(entries) is not list or not 1<=len(entries)<=1000:
        raise ValueError('Expected 1–1000 explicit holdings per range')
    legal=[]; seen=set(); total=0
    for e in entries:
        if type(e) is not dict or set(e)!={'cards','weight'}:
            raise ValueError('Expected cards and integer weight')
        h=tuple(sorted(_cards(e['cards'],5))); w=e['weight']
        if type(w) is not int or not 1<=w<=10**9 or h in seen:
            raise ValueError('Invalid weight or duplicate holding')
        seen.add(h); total+=w
        if not set(h).intersection(board): legal.append((h,w))
    if not legal: raise ValueError('Range completely blocked by board')
    return sorted(legal),total


def compare_ranges(board, range_a, range_b, *, method='auto', trials=2000, seed=0, max_exact=5000):
    """Weighted joint disjoint holdings; equity and board-nut prevalence are distinct."""
    b=board_cards(board)
    if method not in ('auto','exact','monte_carlo') or type(trials) is not int or not 1<=trials<=100000 or type(seed) is not int or not 0<=seed<2**32 or type(max_exact) is not int or not 1<=max_exact<=20000:
        raise ValueError('Invalid enumeration options')
    aa,ta=_range(range_a,b); bb,tb=_range(range_b,b)
    if len(aa)*len(bb)>20000: raise ValueError('Joint range pair budget exceeded')
    nuts=max(pair_ranks(b).values())
    ar={h:evaluate(h,b)['rank'] for h,w in aa}; br={h:evaluate(h,b)['rank'] for h,w in bb}
    legal=[]; nut_a=nut_b=total=0
    for h,w in aa:
        for v,z in bb:
            if set(h).intersection(v): continue
            mass=w*z; total+=mass
            nut_a+=mass*(ar[h]==nuts); nut_b+=mass*(br[v]==nuts)
            legal.append((h,v,mass))
    if not legal: raise ValueError('No disjoint range pairing')
    k=5-len(b); runouts=comb(42-len(b),k); states=len(legal)*runouts
    exact=method=='exact' or (method=='auto' and states<=max_exact)
    if exact and states>max_exact: raise ValueError('Exact enumeration exceeds budget')
    counts=[0,0,0]
    def outcome(h,v,extra):
        if not k: x,y=ar[h],br[v]
        else:
            full=b+tuple(extra); x=evaluate(h,full)['rank']; y=evaluate(v,full)['rank']
        return 0 if x>y else 1 if x==y else 2
    def remaining(h,v):
        blocked=set(b+h+v); return [c for c in DECK if c not in blocked]
    if exact:
        for h,v,w in legal:
            for extra in combinations(remaining(h,v),k): counts[outcome(h,v,extra)]+=w
        denominator=total*runouts
    else:
        rng=random.Random(seed); cum=list(accumulate(w for _,_,w in legal))
        for _ in range(trials):
            h,v,_=legal[bisect_right(cum,rng.randrange(total))]
            counts[outcome(h,v,rng.sample(remaining(h,v),k))]+=1
        denominator=trials
    assert sum(counts)==denominator
    q=Fraction(2*counts[0]+counts[1],2*denominator); point=float(q)
    radius=0 if exact else sqrt(log(40)/(2*trials))
    lo,hi=max(0,point-radius),min(1,point+radius)
    return {'variant':5,'status':'CONDITIONAL_RANGE_COMPARISON','board':list(b),
            'method':'exact' if exact else 'monte_carlo','seed':None if exact else seed,
            'possible_states':states,'evaluated_states':states if exact else trials,
            'legal_pairings':len(legal),'input_joint_weight':ta*tb,'legal_joint_weight':total,
            'excluded_joint_weight':ta*tb-total,'outcome_mass':counts,'mass_denominator':denominator,
            'equity_a':point,'equity_b':float(1-q),'equity_a_fraction':{'numerator':q.numerator,'denominator':q.denominator},
            'equity_a_sampling_ci95':[lo,hi], 'equity_b_sampling_ci95':[1-hi,1-lo],
            'equity_advantage':('A' if lo>.5 else 'B' if hi<.5 else 'TIE' if exact and q==Fraction(1,2) else 'UNCERTAIN'),
            'board_nut_weight_a':nut_a,'board_nut_weight_b':nut_b,
            'board_nut_fraction_a':float(Fraction(nut_a,total)), 'board_nut_fraction_b':float(Fraction(nut_b,total)),
            'nut_advantage':'A' if nut_a>nut_b else 'B' if nut_b>nut_a else 'TIE',
            'nut_definition':'current_absolute_board_nuts_before_private_card_removal',
            'joint_weight_model':'product_weights_conditioned_on_board_and_disjoint_holdings',
            'range_uncertainty_included':False,'future_betting_modeled':False,'gto_solution':False,
            'video_verified':False,'strategic_error_established':False,'frequency':None,'ev_bb':None}
