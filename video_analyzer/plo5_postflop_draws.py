"""Offline PLO5 exact card-completion counts, conditional nuts and decision arithmetic."""
from fractions import Fraction
from itertools import combinations
from collections import Counter
from math import comb
import re

from plo5_board_texture import board_cards, pair_ranks, DECK
from plo5_evaluator import evaluate
from offline_omaha_showdown import _cards, _five, RANKS

TARGETS = ('straight', 'flush', 'full_house', 'quads')


def features(h, b):
    ranks = [_five(p+t) for p in combinations(h,2) for t in combinations(b,3)]
    cats = {r[0] for r in ranks}
    # Existence of legal combinations, not necessarily the best made hand.
    return max(ranks), dict(zip(TARGETS,(bool(cats & {4,8}),bool(cats & {5,8}),6 in cats,7 in cats)))


def odds(n,d):
    return {'count':n,'denominator':d,'probability':float(Fraction(n,d)) if d else None}


def draws(hero, board):
    """Uniform unknown cards conditional only on Hero and board; not win outs."""
    b=board_cards(board); h=_cards(hero,5)
    if set(h).intersection(b): raise ValueError('Private and board overlap')
    h=tuple(sorted(h)); remain=[c for c in DECK if c not in set(h+b)]
    current, made=features(h,b); now=pair_ranks(b,h); ceiling=max(now.values())
    current_nut=current>=ceiling
    nexts={}; nut_cards=[]; absolute_nuts=[]; better=[]; lost_nuts=[]; higher_flush=[]
    if len(b)<5:
        for c in remain:
            future=b+(c,); rank, flags=features(h,future); nexts[c]=flags
            pairs=pair_ranks(future); absolute=max(pairs.values())
            opposing=max(r for p,r in pairs.items() if not set(p).intersection(h))
            if rank>=opposing: nut_cards.append(c)
            elif current_nut: lost_nuts.append(c)
            if rank==absolute: absolute_nuts.append(c)
            if rank>current: better.append(c)
            # Highest possible ordinary flush by suit, ignoring straight flush/full house.
            if flags['flush'] and not made['flush']:
                for suit in 'cdhs':
                    own=sorted((RANKS.index(x[0]) for x in h if x[1]==suit),reverse=True)
                    if len(own)<2 or sum(x[1]==suit for x in future)<3: continue
                    best=sorted((RANKS.index(x[0]) for x in DECK if x[1]==suit and x not in future),reverse=True)[:2]
                    if own[:2]==best: higher_flush.append(c); break
    n=len(nexts); completions={k:[c for c,f in nexts.items() if f[k]] if not made[k] else [] for k in TARGETS}
    union=[c for c in nexts if any(c in completions[k] for k in TARGETS)]
    by_river=Counter(); two_only=Counter(); all_new=0
    d=comb(len(remain),2) if len(b)==3 else n
    if len(b)==3:
        for a,c in combinations(remain,2):
            _, flags=features(h,b+(a,c)); hit=False
            for k in TARGETS:
                if not made[k] and flags[k]:
                    by_river[k]+=1;hit=True
                    if not nexts[a][k] and not nexts[c][k]:two_only[k]+=1
            all_new+=hit
    elif len(b)==4:
        for k in TARGETS: by_river[k]=len(completions[k])
        all_new=len(union)
    targets={k:{'already_possible':made[k], 'next_cards':completions[k],
                'next_completion':odds(len(completions[k]),n) if not made[k] else None,
                'by_river_completion':odds(by_river[k],d) if not made[k] else None,
                'two_card_only_completion':odds(two_only[k],d) if len(b)==3 and not made[k] else None,
                'backdoor_only':len(b)==3 and not made[k] and not completions[k] and two_only[k]>0}
             for k in TARGETS}
    return {'variant':5,'street':{3:'flop',4:'turn',5:'river'}[len(b)],'current_made_hand':evaluate(h,b),
            'unseen_cards':len(remain),'next_card_denominator':n,'river_runout_denominator':d,
            'targets':targets,'combined_new_target_cards':union,'combined_next_completion':odds(len(union),n),
            'combined_by_river_completion':odds(all_new,d),
            'straight_draw_card_count':len(completions['straight']),
            'wrap_heuristic':len(completions['straight'])>8,
            'top_flush_completion_cards':higher_flush,
            'nut_flush_completion_cards':[c for c in completions['flush'] if c in absolute_nuts],
            'current_unbeatable_after_blockers':current_nut,
            'next_unbeatable_after_blockers_cards':nut_cards,'next_absolute_board_nut_cards':absolute_nuts,
            'next_new_unbeatable_cards':nut_cards if not current_nut else [],'next_loses_unbeatable_status_cards':lost_nuts,
            'next_rank_improvement_cards':better,'redraw_rank_improvement_cards':better if current[0]>=2 else [],
            'rank_blockers':[{'rank':r,'hero_count':sum(x[0]==r for x in h),'unseen_count':sum(x[0]==r for x in remain)} for r in reversed(RANKS)],
            'held_card_blockers':list(h),'scope':'hero_board_only_uniform_unknown_cards',
            'outs_are_winning_outs':False,'range_conditioned':False,'gto_solution':False,'video_verified':False}


def decision_math(pot_bb, to_call_bb, hero_remaining_bb, opponent_remaining_bb=None):
    """Decision-time SPR, not necessarily street-start SPR; no rake or future bets."""
    def amount(v):
        if type(v) not in (str,int) or not re.fullmatch(r'\d{1,10}(?:\.\d{1,8})?',str(v)): raise ValueError('Explicit decimal BB required')
        q=Fraction(v)
        if not 0<=q<=10**9: raise ValueError('BB amount out of range')
        return q
    p,c,h=map(amount,(pot_bb,to_call_bb,hero_remaining_bb))
    if not p or c>h or c>p: raise ValueError('Invalid pot/call/stack')
    v=None if opponent_remaining_bb is None else amount(opponent_remaining_bb)
    return {'pot_odds_without_rake':float(c/(p+c)) if c else None,
            'call_equity_threshold_terminal_without_rake':float(c/(p+c)) if c else None,
            'decision_time_remaining_stack_to_pot_ratio':float(min(h,v)/p) if v is not None else None,
            'hero_remaining_stack_to_pot_ratio':float(h/p),
            'spr_scope':'remaining_stacks_at_decision_not_street_start',
            'opponent_stack_known':v is not None,'future_betting_modeled':False,'video_verified':False}
