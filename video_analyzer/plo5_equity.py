"""Offline heads-up PLO5 showdown equity, conditional on explicit holdings/ranges."""
from bisect import bisect_right
from fractions import Fraction
from functools import lru_cache
from itertools import accumulate, combinations
from math import comb, log, sqrt
import random

if __package__:
    from .offline_omaha_showdown import _cards, RANKS, SUITS
    from .plo5_evaluator import evaluate
else:
    from offline_omaha_showdown import _cards, RANKS, SUITS
    from plo5_evaluator import evaluate

DECK = tuple(r+s for r in RANKS for s in SUITS)


def prepare(hero, board, entries):
    h = tuple(sorted(_cards(hero, 5)))
    if not isinstance(board, (list, tuple)) or len(board) not in (0, 3, 4, 5):
        raise ValueError('Expected preflop, flop, turn or river board')
    b = _cards(board, len(board))
    known = set(h+b)
    if len(known) != len(h+b):
        raise ValueError('Hero and board overlap')
    if type(entries) is not list or not 1 <= len(entries) <= 10000:
        raise ValueError('Expected 1–10000 explicit range combos')
    seen, legal = set(), []
    total = blocked = 0
    for e in entries:
        if type(e) is not dict or set(e) != {'cards', 'weight'}:
            raise ValueError('Expected cards and relative integer weight')
        cards = tuple(sorted(_cards(e['cards'], 5)))
        w = e['weight']
        if type(w) is not int or not 1 <= w <= 10**9 or cards in seen:
            raise ValueError('Invalid weight or duplicate combo')
        seen.add(cards)
        total += w
        if known.intersection(cards):
            blocked += w
        else:
            remaining = tuple(c for c in DECK if c not in known and c not in cards)
            legal.append((cards, w, remaining))
    if not legal:
        raise ValueError('All opponent combos blocked')
    audit = {'input_combos':len(entries), 'legal_combos':len(legal),
             'blocked_combos':len(entries)-len(legal), 'input_weight':total,
             'legal_weight':total-blocked, 'blocked_weight':blocked,
             'blocked_weight_fraction':blocked/total, 'renormalized_after_blockers':True}
    return h, b, sorted(legal), audit


def equity(hero, board, entries, *, method='auto', trials=2000, seed=0, max_exact=5000):
    """Choose exact enumeration within a budget, otherwise IID weighted sampling.

    Equal eligible pot, one opponent, no future betting/rake. Integer weights
    are relative masses, not solver action frequencies or inferred ranges.
    """
    if method not in ('auto','exact','monte_carlo'):
        raise ValueError('Unknown method')
    if type(trials) is not int or not 1<=trials<=100000 or type(seed) is not int or not 0<=seed<2**32:
        raise ValueError('Invalid trials or seed')
    if type(max_exact) is not int or not 1<=max_exact<=20000:
        raise ValueError('Invalid exact enumeration budget')
    h,b,legal,audit=prepare(hero,board,entries)
    k=5-len(b)
    runouts=comb(42-len(b),k)
    states=len(legal)*runouts
    exact=method=='exact' or (method=='auto' and states<=max_exact)
    if exact and states>max_exact:
        raise ValueError('Exact enumeration exceeds budget')

    @lru_cache(maxsize=2048)
    def hero_rank(full_board):
        return evaluate(h,full_board)['rank']

    def outcome(villain,extra):
        full=tuple(sorted(b+tuple(extra)))
        a=hero_rank(full); v=evaluate(villain,full)['rank']
        return 0 if a>v else 1 if a==v else 2

    mass=[0,0,0]
    if exact:
        for villain,w,remain in legal:
            for extra in combinations(remain,k):
                mass[outcome(villain,extra)]+=w
        denominator=audit['legal_weight']*runouts
        count=states
    else:
        rng=random.Random(seed)
        cumulative=list(accumulate(w for _,w,_ in legal))
        for _ in range(trials):
            v,_,remain=legal[bisect_right(cumulative,rng.randrange(cumulative[-1]))]
            mass[outcome(v,rng.sample(remain,k))]+=1
        denominator=count=trials
    assert sum(mass)==denominator
    q=Fraction(2*mass[0]+mass[1],2*denominator)
    estimate=float(q)
    radius=0 if exact else sqrt(log(40)/(2*trials))
    return {'variant':5,'method':'exact_weighted_runouts' if exact else 'weighted_monte_carlo',
            'equity':estimate,'equity_fraction':{'numerator':q.numerator,'denominator':q.denominator},
            'win_probability':mass[0]/denominator,'tie_probability':mass[1]/denominator,
            'loss_probability':mass[2]/denominator,
            'outcome_mass':dict(zip(('win','tie','loss'),mass)), 'mass_denominator':denominator,
            'mass_semantics':'integer_weighted_state_mass' if exact else 'sample_count',
            'evaluated_states':count,'possible_states':states,'runouts_per_combo':runouts,
            'seed':None if exact else seed,'sampling_ci95':[max(0,estimate-radius),min(1,estimate+radius)],
            'ci_method':'no_sampling_error' if exact else 'Hoeffding_iid_bounded_payoff',
            'range_audit':audit,'range_is_assumption':True,'range_uncertainty_included_in_ci':False,
            'opponents':1,'gto_solution':False,'video_verified':False,'future_betting_modeled':False}


def known_equity(hero, board, opponent, **options):
    result=equity(hero,board,[{'cards':opponent,'weight':1}],**options)
    return {**result,'opponent_model':'explicit_fixed_holding_assumption'}


def sensitivity(hero, board, scenarios, **options):
    """Compare explicit alternative ranges; span of estimates is NOT a CI."""
    if type(scenarios) is not dict or not 2<=len(scenarios)<=5 or any(type(k) is not str or not k.strip() or len(k)>80 for k in scenarios):
        raise ValueError('Expected 2–5 named range hypotheses')
    results={name:equity(hero,board,entries,**options) for name,entries in scenarios.items()}
    values=[r['equity'] for r in results.values()]
    return {'variant':5,'scenarios':results,'estimate_span':[min(values),max(values)],
            'span_is_confidence_interval':False,'range_hypotheses_verified':False,'gto_solution':False}
