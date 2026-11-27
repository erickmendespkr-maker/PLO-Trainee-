"""Offline PLO5 review. Declared histories and visual candidates stay separate."""
from math import isfinite
from plo5_pre_gto_context import cards,need
from plo5_post_gto_context import normalize
from plo5_post_gto_tree import start,step,advance,bounds
from plo5_strategy_cache import solve_cached,lookup
from plo5_pre_policy_bridge import classify_history,extract
from plo5_reconstruction_candidates import collect


def postflop(cache,context,history,holding,action,*,rake_on_fold,iterations=100,pot_bps=(),
             cfr_executable=None,joint=None,rank_executables=None,rank_reader=None):
    """Root must be a settled street; history contains only events before decision.
    Model EV is relative to the current decision. Never condition on later cards.
    """
    c=normalize(context);h=cards(holding);s=start(context)
    need(type(history) is list and len(history)<=128,'Invalid decision prefix')
    need(type(action) is list and len(action)==2 and type(action[0]) is str and type(action[1]) is int,'Invalid action')
    for e in history:
        need(type(e) is list and len(e)==3,'Invalid history event')
        p,a,v=e
        if p=='chance':
            need(v==0 and a not in h,'Invalid chance or hero blocker');s=advance(s,a)
        else:s=step(s,p,a,v)
    need(s.pending and not set(h)&set(s.board),'Invalid hero decision')
    need(any(r['cards']==h for r in c['ranges'][s.actor]),'Holding absent from modeled range')
    b=bounds(s);step(s,s.actor,*action)  # Validate action even if it is outside discrete tree.
    call=b['call_payment'];odds=call/(s.pot+call) if call else None
    result=dict(status='MODELED_DECISION',variant=5,position=s.actor,holding=h,board=list(s.board),
                action=action,pot_bb=s.pot/s.bb,call_bb=call/s.bb,pot_odds_gross=odds,
                pot_odds_scope='Preço imediato bruto, sem rake, potes laterais ou apostas futuras.',
                ev_bb=None,ev_gap_bb=None,verdict='SEM COMPARAÇÃO',actions=[],
                evidence='DECLARED_INPUT',gto_solution=False,financial_result_verified=False)
    if rank_executables is not None:
        from plo5_rank_service import lookup_states
        result['rank']=lookup_states(rank_executables[0],rank_reader,len(s.board),[(h,list(s.board))],rank_executable=rank_executables[1])[0]
    data=solve_cached(cache,context,iterations,pot_bps,rake_on_fold=rake_on_fold,joint=joint,cfr_executable=cfr_executable)
    r=data['result'];hit=lookup(data,history,h)
    result.update(cache_key=data['cache_key'],cache_hit=data['cache_hit'],backend=r['backend'],iterations=r['iterations'],
                  legal_deals=r['legal_deals'],nashconv_bb=r['nashconv_bb'],model_scope=r['scope'])
    if hit['status']!='CONDITIONAL_POLICY':
        result['status']=hit['status'];return result
    rows=hit['policy']['actions'];result['actions']=rows
    chosen=[a for a in rows if [a['action'],a['amount']]==action]
    if len(chosen)!=1:result['status']='UNMODELED_ACTION';return result
    if not all(type(a['ev_bb']) in (int,float) and isfinite(a['ev_bb']) for a in rows):
        result['status']='UNAVAILABLE_EV';return result
    ev=chosen[0]['ev_bb'];best=max(a['ev_bb'] for a in rows);gap=max(0.,best-ev)
    result.update(ev_bb=ev,ev_gap_bb=gap,best_ev_bb=best,
                  verdict='MENOR EV NO MODELO' if gap>1e-8 else 'MAIOR EV NO MODELO',
                  ev_scope='EV condicional da política média, em BB a partir da decisão; não é resultado realizado nem erro GTO certificado.')
    return result


def preflop(context,policy=None):
    r=classify_history(context)
    out=dict(status='PREFLOP_HISTORY_ONLY',history=r,evidence='DECLARED_INPUT',ev_bb=None,gto_solution=False)
    if policy is not None:
        out['policy_evidence']=extract(context,policy)
        out['status']='PREFLOP_POLICY_UNVERIFIED_PRIOR'
    return out


def visual(manifest):
    need(manifest.get('variant')==5 and manifest.get('hands_reconstructed') is False,'Candidate manifest required')
    r=collect(manifest['frames'])
    return dict(status='VISUAL_EVIDENCE_ONLY',evidence='UNVERIFIED_VIDEO',source_sha256=manifest.get('source_sha256'),
                samples=r['samples'],changes=r['display_changes'],segments=r['card_segments'],breaks=r['breaks'],
                ev_bb=None,gto_solution=False,financial_result_verified=False)


def from_preflop(cache,context,policy,flop,history,holding,action,*,approximate_joint=False,**kwargs):
    from plo5_pre_policy_bridge import prepare
    bridge=prepare(context,flop,policy,approximate_joint=approximate_joint)
    b=bridge['bridge']
    r=postflop(cache,b['post_context'],history,holding,action,rake_on_fold=b['rake_on_fold'],joint=b['joint'],**kwargs)
    r.update(bridge_key=b['bridge_key'],preflop_policy_sha256=bridge['evidence']['source_sha256'],
             training_context_verified=False,joint_weights_exact=b['joint_weights_exact'],joint_weight_tv=b['joint_weight_tv'])
    return r


def declared_settlement(stacks,sb,bb,events,holdings,*,rake_bps,rake_cap,rake_on_fold,observations):
    from plo5_reconstruct_ledger import replay,reconcile
    r=replay(stacks,sb,bb,events,holdings,rake_bps=rake_bps,rake_cap=rake_cap,rake_on_fold=rake_on_fold)
    a=reconcile(r,**observations)
    return dict(status=a['status'],evidence='DECLARED_INPUT',net_bb={p:float(v) for p,v in r['net_bb'].items()} if a['net_chips'] is not None else None,
                errors=a['errors'],ev_bb=None,financial_result_verified=False,gto_solution=False)
