"""Bounded same-street reconstruction from full declared stack snapshots.
A compatible path is not an observed action; no solver authorization.
"""
from plo5_pre_gto_context import need,integer
import plo5_pre_gto_tree as pre
import plo5_post_gto_tree as post


def infer(state,target_stacks,target_pot,*,target_actor=None,actor_known=False,target_active=None,max_steps=4,max_nodes=2000):
    need(isinstance(state,(pre.State,post.State)),'Invalid state')
    need(type(max_steps) is int and 0<=max_steps<=8 and type(max_nodes) is int and 1<=max_nodes<=100000,'Invalid search budget')
    need(type(actor_known) is bool and (not actor_known or target_actor is None or target_actor in state.order),'Invalid actor constraint')
    need(type(target_stacks) is dict and set(target_stacks)==set(state.order),'Complete stack roster required')
    target=tuple(integer(target_stacks[p]) for p in state.order);integer(target_pot)
    need(all(a>=b for a,b in zip(state.remaining,target)),'Increase requires settlement or rebuy evidence')
    need(state.pot+sum(a-b for a,b in zip(state.remaining,target))==target_pot,'Inconsistent displayed pot')
    if target_active is not None:
        need(type(target_active) in (list,tuple) and len(set(target_active))==len(target_active) and set(target_active)<=set(state.order),'Invalid active roster')
        target_active=set(target_active)
    engine=pre if isinstance(state,pre.State) else post
    hits=[];visited=0;exhausted=False
    def walk(s,path):
        nonlocal visited,exhausted
        if visited>=max_nodes:exhausted=True;return
        visited+=1
        if (s.remaining==target and s.pot==target_pot and (not actor_known or s.actor==target_actor)
            and (target_active is None or {s.order[i] for i in s.active}==target_active)):
            hits.append(path)
            if len(hits)>=2:return
        if len(path)>=max_steps or not s.pending or len(hits)>=2:return
        b=engine.bounds(s);i=s.pending[0];limit=s.remaining[i]-target[i]
        call=b['to_call'];choices=[('fold',0),('call',b['call_payment'])] if call else [('check',0)]
        lo,hi=b['raise_min'],b['raise_max']
        def options():
            yield from choices
            if lo is not None:
                for v in range(lo,min(hi,limit)+1):yield ('raise' if engine is pre or call else 'bet',v)
        for a,v in options():
            if v>limit:continue
            nxt=engine.step(s,s.actor,a,v)
            walk(nxt,path+[dict(position=s.actor,action=a,amount=v)])
            if exhausted or len(hits)>=2:return
    walk(state,[])
    status='AMBIGUOUS' if len(hits)>=2 else 'SEARCH_BUDGET_EXCEEDED' if exhausted else 'UNIQUE_WITHIN_STEP_LIMIT' if hits else 'NO_PATH_WITHIN_STEP_LIMIT'
    return dict(status=status,candidates=hits,visited=visited,max_steps=max_steps,actions_verified=False,financial_result_verified=False,strategy_authorized=False)
