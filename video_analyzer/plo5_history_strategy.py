"""Offline bridge: reconciled HU text record -> declared street-root model.
Ranges are supplied explicitly at the street root; never extracted from showdown.
No automatic strategic authorization or GTO certification.
"""
from hashlib import sha256
from plo5_history_replay import reconstruct, HEADER, money
from plo5_pre_gto_context import need, cards
import plo5_pre_gto_tree as pre
import plo5_post_gto_tree as post
from plo5_review import postflop


def prepare(record, event_index, ranges, *, rake_bps, rake_cap, rake_on_fold):
    r=reconstruct(record)
    need(len(r['positions'])==2,'HU only: prior side pots/folded blockers unsupported')
    events=r['events'];need(type(event_index) is int and 0<=event_index<len(events),'Invalid event index')
    e=events[event_index];hero=r['hero_position'];need(e.get('position')==hero,'Select a hero decision')
    sb=money(HEADER.fullmatch(record['raw'].splitlines()[0]).group(2));bb=r['bb_cents']
    s=pre.start(r['stacks_cents'],sb,bb);root=None;history=[]
    for x in events[:event_index]:
        if 'cards' in x:
            if isinstance(s,pre.State):
                need(s.status=='flop_transition','Not a live flop transition')
                order=('BB','SB');ix=[s.order.index(p) for p in order]
                need(len(s.active)==2 and s.paid[0]==s.paid[1],'Unsupported prior pot')
                s=post.State(order,tuple(x['cards']),s.pot,tuple(s.remaining[i] for i in ix),(0,0),(0,0),(False,False),(0,1),(-1,-1),(bb,bb),bb,bb)
            else:
                need(s.status=='chance_transition','Not a live street transition')
                s=post.advance(s,x['cards'][0])
            need(len(s.active)==2 and all(s.remaining) and s.actor==s.order[0],'Unsupported street root')
            root=s;history=[]
        else:
            engine=pre if isinstance(s,pre.State) else post
            s=engine.step(s,x['position'],x['action'],x['amount'])
            if root is not None:history.append([x['position'],x['action'],x['amount']])
    need(root is not None and s.actor==hero,'Postflop hero decision required')
    post.step(s,hero,e['action'],e['amount'])
    # Do not use r.board, r.awards, or shown opponent cards to construct the model.
    c=dict(variant=5,board=list(root.board),seats=list(root.order),actor=root.actor,pot=root.pot,bb=bb,
           stacks=dict(zip(root.order,root.remaining)),ranges=ranges,rake_bps=rake_bps,rake_cap=rake_cap,
           tree_version=post.VERSION,continuation_version='text-street-root-v1')
    from plo5_post_gto_context import normalize
    n=normalize(c);h=cards(record['holding'])
    need(any(row['cards']==h for row in n['ranges'][hero]),'Hero holding absent from supplied range')
    need(type(rake_on_fold) is bool,'Explicit rake rule required')
    return dict(context=c,history=history,holding=h,action=[e['action'],e['amount']],rake_on_fold=rake_on_fold)


def review(cache,record,event_index,ranges,*,rake_bps,rake_cap,rake_on_fold,**kwargs):
    model=prepare(record,event_index,ranges,rake_bps=rake_bps,rake_cap=rake_cap,rake_on_fold=rake_on_fold)
    result=postflop(cache,**model,**kwargs)
    return dict(result,source_record_sha256=sha256(record['raw'].encode('utf-8')).hexdigest(),
                event_index=event_index,evidence='RECONCILED_TEXT_DECLARED_RANGES',range_provenance_verified=False,
                source_truth_verified=False,strategy_authorized=False)


def main(argv=None):
    import argparse,json
    from pathlib import Path
    from plo5_history_intake import intake
    from plo5_review_session import read_json,review_batch,model_page
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source');p.add_argument('config');p.add_argument('output');p.add_argument('--cache',required=True);p.add_argument('--native');p.add_argument('--rank');a=p.parse_args(argv)
    out=Path(a.output);need(out.suffix.lower()=='.html' and not out.exists() and not out.is_symlink(),'New HTML required')
    parsed=intake(a.source);records={r['id']:r for r in parsed['hands']};d,_=read_json(a.config)
    need(set(d)=={'decisions'} and type(d['decisions']) is list and 1<=len(d['decisions'])<=64,'Invalid decision batch')
    required={'hand_id','event_index','ranges','rake_bps','rake_cap','rake_on_fold'};models=[]
    for spec in d['decisions']:
        need(type(spec) is dict and required<=set(spec)<=required|{'iterations','pot_bps'},'Invalid decision fields')
        ident=spec['hand_id'];need(type(ident) is str and ident in records,'Unknown hand ID')
        m=prepare(records[ident],spec['event_index'],spec['ranges'],rake_bps=spec['rake_bps'],rake_cap=spec['rake_cap'],rake_on_fold=spec['rake_on_fold'])
        models.append(dict(m,id=f'Mão {ident} / evento {spec["event_index"]}',**{k:spec[k] for k in ('iterations','pot_bps') if k in spec}))
    if a.rank:
        from plo5_rank_worker import RankWorker
        with RankWorker(a.rank) as w:rows=review_batch(a.cache,models,cfr_executable=a.native,rank_worker=w)
    else:rows=review_batch(a.cache,models,cfr_executable=a.native)
    html=model_page(rows).replace('<h1>PLO Trainee — Revisão pós-sessão</h1>','<h1>PLO Trainee — Revisão pós-sessão</h1><p>Histórico textual conciliado; ranges e rake do modelo declarados, não verificados. SHA-256 da fonte: '+parsed['source_sha256']+'</p>',1)
    with out.open('x',encoding='utf-8') as f:f.write(html)
    print(json.dumps(dict(status='RECONCILED_TEXT_DECLARED_RANGES',decisions=len(rows),strategy_authorized=False)));return 0

if __name__=='__main__':raise SystemExit(main())
