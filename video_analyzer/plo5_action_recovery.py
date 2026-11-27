"""Offline bounded action recovery between declared complete chip snapshots.
No OCR inference, chance, settlement or rebuy inside a search interval.
A unique candidate within the declared bounds is not a verified video action.
"""
from plo5_pre_gto_context import need, integer
import plo5_pre_gto_tree as pre
import plo5_post_gto_tree as post


UNKNOWN_ACTOR = object()


def recover(state, remaining, pot, *, folded=None, expected_actor=UNKNOWN_ACTOR,
            expected_status=None, max_actions=6, max_nodes=20000):
    need(isinstance(state,(pre.State,post.State)), 'Invalid betting state')
    need(type(remaining) is dict and set(remaining)==set(state.order),'Complete stack roster required')
    target=tuple(integer(remaining[p]) for p in state.order);integer(pot)
    need(type(max_actions) is int and 0<=max_actions<=12 and type(max_nodes) is int and 1<=max_nodes<=100000,'Invalid search budget')
    need(all(a>=b for a,b in zip(state.remaining,target)),'Stack increase: settlement/rebuy not modeled')
    need(state.pot+sum(a-b for a,b in zip(state.remaining,target))==pot,'Chip conservation mismatch')
    if folded is not None:
        need(type(folded) is dict and set(folded)==set(state.order) and all(type(v) is bool for v in folded.values()),'Invalid folded roster')
        target_fold=tuple(folded[p] for p in state.order)
        need(all(not a or b for a,b in zip(state.folded,target_fold)),'Fold reversal')
    else:target_fold=None
    need(expected_actor is UNKNOWN_ACTOR or expected_actor is None or expected_actor in state.order,'Invalid expected actor')
    need(expected_status is None or expected_status in ('decision','fold_terminal','flop_transition','chance_transition','all_in_showdown','river_showdown'),'Invalid expected status')
    rules=pre if isinstance(state,pre.State) else post
    visited=0;truncated=False;hits=[]
    def visit(s,path):
        nonlocal visited,truncated
        if len(hits)>=2:return
        if visited>=max_nodes:truncated=True;return
        visited+=1
        if (s.remaining==target and s.pot==pot and (target_fold is None or s.folded==target_fold)
            and (expected_actor is UNKNOWN_ACTOR or s.actor==expected_actor)
            and (expected_status is None or s.status==expected_status)):hits.append(path)
        if len(hits)>=2 or not s.pending:return
        if len(path)>=max_actions:
            # A depth limit is part of the declared model, not proof about real history.
            return
        i=s.pending[0];limit=s.remaining[i]-target[i];b=rules.bounds(s)
        aa=[('fold',0),('call',b['call_payment'])] if b['to_call'] else [('check',0)]
        lo,hi=b['raise_min'],b['raise_max']
        if lo is not None:
            hi=min(hi,limit)
        aggressive='raise' if rules is pre or b['to_call'] else 'bet'
        def try_action(a,v):
            if v>limit or (a=='fold' and target_fold is not None and not target_fold[i]):return
            event=dict(position=s.actor,action=a,amount=v)
            child=rules.step(s,s.actor,a,v)
            visit(child,path+[event])
        for a,v in aa:try_action(a,v)
        if lo is not None and hi>=lo:
            for v in range(lo,hi+1):
                if len(hits)>=2 or visited>=max_nodes:
                    if visited>=max_nodes:truncated=True
                    break
                try_action(aggressive,v)
    visit(state,[])
    status='AMBIGUOUS' if len(hits)>1 else 'SEARCH_BUDGET_EXCEEDED' if truncated else 'UNIQUE_WITHIN_BOUNDS' if hits else 'NO_MATCH_WITHIN_BOUNDS'
    return dict(status=status,candidates=hits,visited=visited,max_actions=max_actions,max_nodes=max_nodes,
                action_verified=False,financial_result_verified=False,strategy_authorized=False)
