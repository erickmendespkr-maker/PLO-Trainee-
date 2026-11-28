"""Offline PLO5 reconstruction hypotheses from audited visual observations."""
import argparse
import json
from collections import Counter
from fractions import Fraction
from pathlib import Path
from statistics import median
from plo5_mixed_money import STARTS
from plo5_pre_gto_context import need, integer, cards
from plo5_reconstruction_candidates import state as card_state
from plo5_snapshot_replay import positions, chips, reveal, SEATS, STREET
from plo5_error_prints import frame_index, groups, decode, bind, stamp, read
from plo5_video_stream import digest
from plo5_selective_review import action_key, select
import plo5_pre_gto_tree as pre
import plo5_post_gto_tree as post

BACK='card_backs_visible_candidate'
EMPTY='explicit_empty_marker_candidate'
LABELS={'fold','check','call','bet','raise','all_in'}


def hero_turn(image,table,platform):
    """PPP three-button color signature; absence is unknown, not opponent turn."""
    if platform!='pppoker':return None
    x=STARTS[table-1]
    colors=[tuple(median(v[i] for v in image.crop((x+a,657,x+a+8,663)).getdata()) for i in range(3)) for a in (17,142,264)]
    (r,g,b),(r2,g2,b2),(r3,g3,b3)=colors
    return 'hero_bottom' if r>=g+35 and r>=b+35 and g2>=r2+30 and g2>=b2+5 and r3>=b3+45 and g3>=b3+35 and r3>=g3 else None

def observe(source,coarse,refined,table,money_reader,card_reader,seat_reader,dealt_reader,*,limit=128):
    """Re-read exact coarse/refined pixels; do not merge observations across PTS."""
    need(type(table) is int and 1<=table<=4 and type(limit) is int and 1<=limit<=512,'Invalid observation budget')
    source=Path(source);need(source.is_file() and not source.is_symlink() and source.suffix.lower()=='.mp4','Local MP4 required')
    frames=frame_index(coarse);h=digest(source);need(h==coarse['source_sha256'],'Source mismatch')
    if refined is not None:
        need(refined.get('version')=='plo5-card-refinement-v1' and refined['source_sha256']==h,'Refinement source mismatch')
        for p,f in frame_index(refined).items():
            need(p not in frames,'Duplicate refinement PTS')
            if table in f['target_tables']:frames[p]=f
    need(0<len(frames)<=limit,'Split observation window');out=[]
    def consume(p,im):
        obs=money_reader.scan(im);cr=card_reader.scan(im);seats=seat_reader.scan(im)
        c=next(x for x in cr if x['table_id']==table);s=next(x for x in seats if x['table_id']==table);d=dealt_reader(im,table)
        need(c['platform']==s['platform']==d['platform'],'Layout mismatch')
        out.append(dict(pts=str(p),file='observed_%05d.rgb'%len(out),rgb_sha256=frames[p]['rgb_sha256'],observations=obs,cards=[dict(c,seat_evidence=s,opponent_evidence=d,actor_candidate=hero_turn(im,table,c['platform']))]))
    expected={p:f['rgb_sha256'] for p,f in frames.items()}
    for batch in groups(frames):decode(source,batch,expected,consume,120)
    need(digest(source)==h,'Source changed')
    return dict(variant=5,source_sha256=h,frames=out,table_id=table,actions_verified=False,strategy_authorized=False)


def snapshot(frame,table,bb,*,partial=False):
    c=next(x for x in frame['cards'] if x['table_id']==table);h=card_state(c);e=c['seat_evidence'];d=c['opponent_evidence']
    need(c['platform'] in ('pppoker','suprema') and e['platform']==d['platform']==c['platform'] and e['table_id']==d['table_id']==table,'Layout unavailable')
    need([s['seat'] for s in e['seats']]==list(SEATS),'Seat roster mismatch')
    opp={x['seat']:x['status'] for x in d['opponents']};need(len(d['opponents'])==5 and set(opp)==set(SEATS)-{'hero_bottom'},'Opponent roster mismatch')
    obs={r['field']:r for r in frame['observations'] if r['table_id']==table};need(set(obs)=={'stack','pot'} and all(r['platform']==c['platform'] and r['layout_candidate_active'] is True for r in obs.values()),'Money layout mismatch')
    def unit(v):return None if v is None else chips(v,bb)
    st={s['seat']:unit(s['stack']['candidate']) for s in e['seats']};hero=unit(obs['stack']['value_bb']);pot=unit(obs['pot']['value_bb'])
    need(hero is not None and hero==st['hero_bottom'],'Hero stack not corroborated')
    need(partial or h is not None and pot is not None,'Missing cards or pot')
    holding=cards(c['hero_cards']) if c.get('hero_cards') is not None else None
    board=c.get('board_cards');need(board is None or type(board) is list and len(board) in STREET,'Invalid board')
    need(c.get('actor_candidate') in (None,'hero_bottom'),'Invalid actor marker')
    return dict(pts=frame['pts'],platform=c['platform'],profile=c.get('rank_profile'),holding=holding,board=board,remaining=st,pot=pot,button=e['dealer']['seat'],opponents=opp,actor=c.get('actor_candidate'),labels={s['seat']:s['action']['candidate'] for s in e['seats']})


def seed_from(s,table,sb,bb):
    """Conditional standard-blind seed; never equate missing stack with vacancy."""
    need(s['board']==[] and s['pot']==sb+bb,'Not a posted-blind candidate')
    need(all(v in (BACK,EMPTY) for v in s['opponents'].values()),'Unresolved dealt roster')
    dealt=[k for k in SEATS if k=='hero_bottom' or s['opponents'].get(k)==BACK];mapping=positions(dealt,s['button']);initial={}
    for k,p in mapping.items():
        v=s['remaining'][k];need(v is not None,'Missing dealt stack');initial[k]=v+(sb if p=='SB' else bb if p=='BB' else 0)
    for k in set(SEATS)-set(dealt):need(s['remaining'][k] is None,'Empty marker conflicts with stack')
    for k,label in s['labels'].items():
        if label in ('sb_label','bb_label'):need(mapping.get(k)==label[:2].upper(),'Blind label conflict')
        need(label not in LABELS,'Voluntary action label at seed')
    return dict(hand_id='candidate-%s-%s'%(table,s['pts']),table_id=table,dealt=dealt,button=s['button'],initial=initial,sb=sb,bb=bb,pot_includes_pending=True,holding=s['holding'])


def recover(s,target,pot,*,active=(),folded=(),labels=None,expected_actor=None,checkpoints=(),max_actions=4,max_nodes=20000):
    """Legal integer paths with partial fold evidence and fresh label constraints."""
    need(type(max_actions) is int and 0<=max_actions<=12 and type(max_nodes) is int and 1<=max_nodes<=100000,'Invalid search budget')
    labels={} if labels is None else labels;need((set(active)|set(folded)|set(labels))<=set(s.order) and not set(active)&set(folded) and all(a in LABELS for a in labels.values()),'Invalid evidence constraints')
    need(expected_actor is None or expected_actor in s.order,'Invalid actor evidence');need(set(target)==set(s.order),'Incomplete stack roster');t=tuple(integer(target[p]) for p in s.order);integer(pot)
    if any(a<b for a,b in zip(s.remaining,t)):return dict(status='PAYOUT_OR_REBUY_UNRESOLVED',paths=[],visited=0)
    if s.pot+sum(a-b for a,b in zip(s.remaining,t))!=pot:return dict(status='DISPLAY_NOT_CONSERVED',paths=[],visited=0)
    engine=pre if isinstance(s,pre.State) else post;hits=[];visited=0;truncated=False
    need(type(checkpoints) in (list,tuple) and len(checkpoints)<=6,'Invalid checkpoint budget')
    for cp in checkpoints:
        need(set(cp['remaining'])<=set(s.order) and set(cp['active'])<=set(s.order) and (cp['actor'] is None or cp['actor'] in s.order),'Invalid checkpoint roster')
    def matches(st,cp):
        return (cp['pot'] is None or st.pot==cp['pot']) and (cp['actor'] is None or st.actor==cp['actor']) and all(st.remaining[st.order.index(p)]==v for p,v in cp['remaining'].items()) and all(not st.folded[st.order.index(p)] for p in cp['active'])
    def visit(st,path,last,k):
        nonlocal visited,truncated
        if len(hits)>=2:return
        if visited>=max_nodes:truncated=True;return
        visited+=1
        if any(st.folded[st.order.index(p)] for p in active):return
        while k<len(checkpoints) and matches(st,checkpoints[k]):k+=1
        if k==len(checkpoints) and st.remaining==t and (expected_actor is None or st.actor==expected_actor) and all(st.folded[st.order.index(p)] for p in folded) and all(last.get(p)==v or v=='all_in' and last.get(p) in ('call','bet','raise') and st.remaining[st.order.index(p)]==0 for p,v in labels.items()):hits.append(path)
        if len(hits)>=2 or not st.pending or len(path)>=max_actions:return
        i=st.pending[0];p=st.actor;b=engine.bounds(st);cap=st.remaining[i]-t[i]
        aa=[('fold',0),('call',b['call_payment'])] if b['to_call'] else [('check',0)]
        def attempt(a,v):
            if v<=cap and not(a=='fold' and p in active):visit(engine.step(st,p,a,v),path+[dict(position=p,action=a,amount=v)],dict(last,**{p:a}),k)
        for a,v in aa:attempt(a,v)
        if b['raise_min'] is not None:
            for v in range(b['raise_min'],min(cap,b['raise_max'])+1):
                if len(hits)>=2 or visited>=max_nodes:
                    if visited>=max_nodes:truncated=True
                    break
                attempt('raise' if engine is pre or b['to_call'] else 'bet',v)
    visit(s,[],{},0);status='AMBIGUOUS' if len(hits)>1 else 'SEARCH_BUDGET_EXCEEDED' if truncated else 'UNIQUE_WITHIN_BOUNDS' if hits else 'NO_MATCH_WITHIN_BOUNDS'
    return dict(status=status,paths=hits,visited=visited)


def reconstruct(manifest,table,*,sb=5,bb=10,max_gap=Fraction(2),max_actions=4,max_nodes=20000):
    """Scan without annotations; all seeds and actions remain conditional."""
    integer(sb,1);integer(bb,1);need(sb<bb and type(table) is int and 1<=table<=4,'Invalid blinds/table');need(0<max_gap<=3,'Invalid gap')
    frames=frame_index(manifest);counts=Counter();hands=[];records=[];current=None;last_seed=None;pending=[]
    def close(reason):
        nonlocal current,pending
        if current is not None:
            current['end_reason']=reason;current['unresolved_checkpoint_pts']=[c['pts'] for c in pending];current['terminal_candidate']=s.status;current['hand_verified']=False;counts['END_'+reason]+=1;hands.append(current);current=None;pending=[]
    for p,f in frames.items():
        try:x=snapshot(f,table,bb,partial=True)
        except ValueError as exc:counts[str(exc)]+=1;close('INCOMPLETE_OBSERVATION');continue
        complete=x['holding'] is not None and x['board'] is not None and x['pot'] is not None
        counts['complete_snapshots' if complete else 'partial_snapshots']+=1
        if current is not None:
            if p-stamp(old['pts'])>max_gap or (x['platform'],x['profile'],x['button'])!=(old['platform'],old['profile'],old['button']) or x['holding'] is not None and x['holding']!=old['holding']:close('CONTINUITY_UNKNOWN')
            elif x['board'] is not None and x['board'][:len(old['board'])]!=old['board']:close('BOARD_RESET_OR_CONFLICT')
        if current is None:
            if not complete:continue
            signature=(x['platform'],x['profile'],x['button'],tuple(x['holding']))
            if signature==last_seed:counts['REPEATED_SEED_SKIPPED']+=1;continue
            try:sd=seed_from(x,table,sb,bb);mapping=positions(sd['dealt'],sd['button']);s=pre.start({v:sd['initial'][k] for k,v in mapping.items()},sb,bb)
            except ValueError as exc:counts[str(exc)]+=1;continue
            if x['actor'] is not None and mapping[x['actor']]!=s.actor:counts['SEED_ACTOR_CONFLICT']+=1;continue
            last_seed=signature;current=dict(seed=sd,positions=mapping,events=[],intervals=[],first_pts=x['pts'],last_pts=x['pts'],next_actor_candidate=s.actor);old=x;counts['seed_candidates']+=1;continue
        target={v:x['remaining'][k] for k,v in mapping.items()}
        if any(x['opponents'].get(k)==BACK for k in set(SEATS)-set(mapping)):close('ROSTER_CONFLICT');continue
        active=[v for k,v in mapping.items() if x['opponents'].get(k)==BACK]
        labels={v:x['labels'][k] for k,v in mapping.items() if x['labels'][k] in LABELS and x['labels'][k]!=old['labels'][k]}
        cp=dict(pts=x['pts'],remaining={v:n for v,n in target.items() if n is not None},pot=x['pot'],active=active,actor=mapping.get(x['actor']))
        if not complete or any(v is None for v in target.values()):
            # Keep only compatible partial observations as constraints, never impute cards.
            if labels or len(pending)>=6 or x['board'] is not None and x['board']!=old['board'] or any(cp['remaining'].get(v,0)>s.remaining[i] for i,v in enumerate(s.order)):
                close('INCOMPLETE_OBSERVATION');continue
            pending.append(cp);counts['DEFERRED_PARTIAL']+=1;continue
        if any(target[v]>s.remaining[i] for i,v in enumerate(s.order)):close('PAYOUT_OR_REBUY_UNRESOLVED');continue
        if x['board']!=old['board']:
            if pending:close('UNANCHORED_STREET');continue
            try:nxt=reveal(s,x['board'][len(old['board']):]);need(len(x['board'])==len(nxt.board),'Skipped street')
            except ValueError:close('UNANCHORED_STREET');continue
            if target!=dict(zip(nxt.order,nxt.remaining)) or x['pot']!=nxt.pot or x['actor'] is not None and mapping[x['actor']]!=nxt.actor or labels:close('UNANCHORED_STREET');continue
            s=nxt;current['events'].append(dict(cards=x['board'][len(old['board']):]));old=x;current['last_pts']=x['pts'];current['next_actor_candidate']=s.actor;continue
        folded=[v for v,a in labels.items() if a=='fold']
        if set(active)&set(folded):close('CONFLICTING_FOLD_EVIDENCE');continue
        r=recover(s,target,x['pot'],active=active,folded=folded,labels=labels,expected_actor=mapping.get(x['actor']),checkpoints=pending,max_actions=max_actions,max_nodes=max_nodes)
        counts[r['status']]+=1;current['intervals'].append(dict(before_pts=old['pts'],after_pts=x['pts'],status=r['status'],visited=r['visited'],checkpoint_pts=[c['pts'] for c in pending]))
        if r['status']=='AMBIGUOUS' and not labels and len(pending)<6:
            pending.append(cp);counts['DEFERRED_AMBIGUOUS']+=1;continue
        if r['status']!='UNIQUE_WITHIN_BOUNDS':close(r['status']);continue
        pending=[]
        engine=pre if isinstance(s,pre.State) else post
        for j,e in enumerate(r['paths'][0]):
            if e['position']==mapping['hero_bottom']:
                b=engine.bounds(s);call=b['call_payment'];d=dict(hand_id=current['seed']['hand_id'],decision_id=str(len(current['events'])),street=STREET[len(old['board'])],action=action_key([e['action'],e['amount']]),pot_odds=call/(s.pot+call) if call else None,reconstruction_verified=False,strategy_verified=False,action_set_complete=False,action_ev_bounds={})
                d['evidence']=bind(manifest,d,old['pts'],table,'before',index=frames) if j==0 else None;records.append(d)
            s=engine.step(s,e['position'],e['action'],e['amount']);current['events'].append(e)
        old=x;current['last_pts']=x['pts'];current['next_actor_candidate']=s.actor
        if s.status=='fold_terminal' or len(x['board'])==5 and s.status in ('all_in_showdown','river_showdown'):close('TERMINAL_CANDIDATE')
    close('WINDOW_END')
    return dict(version='plo5-auto-reconstruction-candidates-v1',counts=dict(counts),hands=hands,decision_records=records,selection=select(records),hands_reconstructed=False,strategy_authorized=False,financial_result_verified=False)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('video');p.add_argument('coarse');p.add_argument('output');p.add_argument('--refined');p.add_argument('--table',type=int,required=True);p.add_argument('--ppp');p.add_argument('--suprema');p.add_argument('--backend',choices=('cli','native'),default='cli');p.add_argument('--bb-units',type=int,default=10);p.add_argument('--sb-units',type=int,default=5);a=p.parse_args(argv)
    from plo5_fast_money import FastMoneyReader
    from plo5_mixed_cards_v2 import MixedCardReader
    from plo5_seat_evidence import SeatReader
    from plo5_dealt_candidates import observe as dealt
    out=Path(a.output);need(out.suffix=='.json' and not out.exists() and not out.is_symlink(),'New JSON required')
    m=read(a.coarse);r=read(a.refined) if a.refined else None
    banks={k:digest(v) for k,v in [('pppoker',a.ppp),('suprema',a.suprema)] if v}
    with FastMoneyReader(workers=2,backend=a.backend) as money:obs=observe(a.video,m,r,a.table,money,MixedCardReader(a.ppp,a.suprema),SeatReader(workers=3),dealt)
    need(all(digest(v)==banks[k] for k,v in [('pppoker',a.ppp),('suprema',a.suprema)] if v),'Bank changed');obs['card_bank_sha256']=banks
    result=dict(observations=obs,reconstruction=reconstruct(obs,a.table,sb=a.sb_units,bb=a.bb_units))
    with out.open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,allow_nan=False,indent=2)
    print(json.dumps(result['reconstruction']['counts']));return 0

if __name__=='__main__':raise SystemExit(main())
