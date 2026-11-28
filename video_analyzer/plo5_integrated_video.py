"""Offline bounded PLO5 candidate pipeline; no automatic strategy certification."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from fractions import Fraction
import json
import os
from pathlib import Path
import tempfile
from time import perf_counter
from plo5_pre_gto_context import need
from plo5_beta_video import probe, write_json
from plo5_bounded_session import run as scan_session, load_interval, windows
from plo5_card_refine import refine
from plo5_error_prints import frame_index, groups, decode, capture, read
from plo5_video_stream import digest
from plo5_selective_review import select, street_filter, STREETS, VERSION, action_key
from plo5_selective_study_report import build
from plo5_auto_reconstruct import ReconstructionStream, hero_turn, panel_evidence
from plo5_seat_evidence import SeatReader, SEATS, STACKS, ACTIONS, STARTS, detect, dealer
from plo5_terminal_bounds import review as terminal_review
from plo5_continuation_bounds import review as continuation_review
from plo5_display_transitions import DisplayTransitions
from plo5_snapshot_replay import positions, reveal
from plo5_decision_math import evaluate_model
import plo5_pre_gto_tree as pre
import plo5_post_gto_tree as post


class Cancelled(Exception):pass


class SharedSeatReader(SeatReader):
    """Same ROI keys and recognition as Macro15; only selected tables, persistent pool."""
    def __init__(self,**kwargs):
        super().__init__(**kwargs);self.pool=ThreadPoolExecutor(max_workers=self.workers)
    def close(self):self.pool.shutdown(wait=True)
    def scan(self,image,tables):
        need(image.size==(1504,696) and image.mode=='RGB','Unsupported geometry');rows=[];jobs=[]
        for t in sorted(tables):
            p=detect(image,t);row=dict(table_id=t,platform=p,dealer=dealer(image,t,p) if p else None,seats=[],positions_verified=False,actions_verified=False,financial_result_verified=False);rows.append(row)
            if p is None:continue
            for i,s in enumerate(SEATS):
                seat=dict(seat=s);row['seats'].append(seat)
                for f,boxes in [('stack',STACKS),('action',ACTIONS)]:
                    a,b,c,d=boxes[p][i];x=STARTS[t-1];patch=image.crop((x+a,b,x+c,d));jobs.append((seat,p,f,patch))
        def read(job):
            seat,p,f,patch=job;key=(p,f,patch.size,patch.tobytes());seat[f]=self.cache.get(key,lambda:self.action_bank.match(patch,p) if f=='action' and self.action_bank is not None else self.decoder(patch,p,f))
        list(self.pool.map(read,jobs));return rows


def observe_shared(source,coarse,refined,tables,money,card,seat,dealt,*,cancel=lambda:None):
    """One exact RGB decode per requested PTS, one shared scan per reader.
    Refined timestamps affect only their target tables; never mix different PTS.
    """
    need(type(tables) in (list,tuple) and 1<=len(tables)<=4 and len(set(tables))==len(tables) and all(type(t) is int and 1<=t<=4 for t in tables),'Invalid table filter')
    source=Path(source);h=digest(source);need(h==coarse['source_sha256'],'Source mismatch')
    frames=frame_index(coarse);targets={p:set(tables) for p in frames}
    if refined is not None:
        need(refined.get('version')=='plo5-card-refinement-v1' and refined['source_sha256']==h,'Refinement source mismatch')
        for p,f in frame_index(refined).items():
            need(p not in frames,'Duplicate refinement PTS');ts=set(tables)&set(f['target_tables'])
            if ts:frames[p]=f;targets[p]=ts
    need(0<len(frames)<=512,'Split observation window');out=[]
    def consume(p,im):
        cancel();obs=money.scan(im);cr={x['table_id']:x for x in card.scan(im)};seats={x['table_id']:x for x in seat.scan(im,targets[p])};rows=[]
        for t in sorted(targets[p]):
            c=cr[t];s=seats[t];d=dealt(im,t);need(c['platform']==s['platform']==d['platform'],'Layout mismatch')
            rows.append(dict(c,seat_evidence=s,opponent_evidence=d,actor_candidate=hero_turn(im,t,c['platform']),panel_evidence=panel_evidence(im,t,c['platform'])))
        out.append(dict(pts=str(p),file='observed_%05d.rgb'%len(out),rgb_sha256=frames[p]['rgb_sha256'],observations=obs,cards=rows))
    for batch in groups(frames):
        cancel();decode(source,batch,{p:frames[p]['rgb_sha256'] for p in batch},consume,120)
    need(digest(source)==h,'Source changed')
    return dict(variant=5,source_sha256=h,frames=out,actions_verified=False,strategy_authorized=False)


def table_manifest(observations,t):
    return dict(variant=5,source_sha256=observations['source_sha256'],frames=[f for f in observations['frames'] if any(c['table_id']==t for c in f['cards'])])


def cfr_review(result,configs,streets,cache,*,native=None,rank=None,cancel=lambda:None):
    """Derive the flop prior root and exact public prefix from recovered events.
    Configs supply ranges, not future cards or a caller-selected tree/history.
    """
    out=[];selected=set(streets)
    for hand in result['hands']:
        sd=hand['seed'];ident=sd['hand_id'];cfg=configs.get(ident);mapping=positions(sd['dealt'],sd['button']);s=pre.start({p:sd['initial'][k] for k,p in mapping.items()},sd['sb'],sd['bb']);root=None;history=[];street_root=s
        if cfg is not None:need(type(cfg) is dict and {'ranges','rake_bps','rake_cap','rake_on_fold'}<=set(cfg)<={'ranges','rake_bps','rake_cap','rake_on_fold','iterations','pot_bps','joint','max_runouts'},'Invalid CFR config')
        ids={d['decision_id']:d for d in result['decision_records'] if d['hand_id']==ident}
        for j,e in enumerate(hand['events']):
            if 'cards' in e:
                was_pre=isinstance(s,pre.State);s=reveal(s,e['cards']);street_root=s
                if was_pre and cfg is not None and len(s.active)==len(s.order) and all(s.remaining) and len(set(s.total_paid))==1 and s.actor==s.order[0]:
                    root=dict(variant=5,board=list(s.board),seats=list(s.order),actor=s.actor,pot=s.pot,bb=s.bb,stacks=dict(zip(s.order,s.remaining)),ranges=cfg['ranges'],rake_bps=cfg['rake_bps'],rake_cap=cfg['rake_cap'],tree_version=post.VERSION,continuation_version='auto-flop-prior-v1')
                elif root is not None:history.append(['chance',e['cards'][0],0])
                continue
            engine=pre if isinstance(s,pre.State) else post;d=ids.get(str(j))
            if d is not None and d['street'] in selected:
                cancel();need(s.actor==mapping['hero_bottom'] and d['action']==action_key([e['action'],e['amount']]),'Decision mismatch');b=engine.bounds(s);i=s.pending[0];call=b['call_payment']
                row=dict(hand_id=ident,decision_id=str(j),street=d['street'],position=s.actor,board=[] if engine is pre else list(s.board),pot_bb=s.pot/s.bb,call_bb=call/s.bb,pot_odds_gross=call/(s.pot+call) if call else None,effective_remaining_bb_by_opponent={s.order[k]:min(s.remaining[i],s.remaining[k])/s.bb for k in s.active if k!=i},hu_spr_street_start=min(street_root.remaining)/street_root.pot if len(street_root.order)==2 and street_root.pot else None,status='NO_DECLARED_FLOP_PRIOR' if cfg is None else 'NO_SUPPORTED_POSTFLOP_ROOT')
                if root is not None:
                    m=dict(context=root,history=list(history),holding=sd['holding'],action=[e['action'],e['amount']],**{k:v for k,v in cfg.items() if k in ('rake_on_fold','iterations','pot_bps','joint')})
                    try:a=evaluate_model(cache,m,cfr_executable=native,rank_worker=rank,max_runouts=cfg.get('max_runouts',20000))
                    except ValueError as exc:row.update(status='MODEL_UNAVAILABLE',reason=str(exc))
                    else:row.update(status='EXPERIMENTAL_MODEL_ONLY',estimate=a)
                out.append(row)
            s=engine.step(s,e['position'],e['action'],e['amount'])
            if root is not None:history.append([e['position'],e['action'],e['amount']])
    return out


def run(source,output,*,start=None,seconds=None,session=None,chunk=20,tables=(1,2,3,4),streets=STREETS,workers=2,backend='cli',seat_backend='cli',ppp=None,suprema=None,refine_budget=8,configs=None,cache=None,native=None,rank=None,cancel_file=None,progress=None,observations_from=None):
    from plo5_fast_money import FastMoneyReader
    from plo5_mixed_cards_v2 import MixedCardReader
    from plo5_dealt_candidates import observe as dealt
    need(type(chunk) is int and 2<=chunk<=60 and type(refine_budget) is int and 0<=refine_budget<=32,'Invalid window/refinement budget')
    selected=street_filter(streets);need(type(tables) in (tuple,list) and 1<=len(tables)<=4 and len(set(tables))==len(tables) and all(type(t) is int and 1<=t<=4 for t in tables),'Invalid tables')
    need(seat_backend in ('cli','native'),'Invalid seat backend');need(ppp or suprema or observations_from is not None,'Provide at least one card bank or prior observations');source=Path(source);out=Path(output);need(not out.exists() and not out.is_symlink() and out.parent.is_dir(),'New output required');duration=probe(source);h=digest(source)
    cfg={'terminal':{},'cfr':{},'bounds':{}} if configs is None else configs;need(type(cfg) is dict and {'terminal','cfr'}<=set(cfg)<={'terminal','cfr','bounds'} and all(type(x) is dict and len(x)<=512 for x in cfg.values()),'Invalid config roster');cfg=dict(cfg,bounds=cfg.get('bounds',{}));need(not cfg['cfr'] or cache is not None,'CFR cache required')
    banks={k:digest(v) for k,v in [('pppoker',ppp),('suprema',suprema)] if v};t0=perf_counter();counts=Counter();rows=[];used=set()
    reused=None;prior_root=None;prior_hash=None;prior_files={}
    if observations_from is not None:
        from plo5_acceptance import audit,load
        need(session is None and start is None and seconds is None and not banks,'Reanalysis uses the exact prior interval and banks')
        prior_root=Path(observations_from);prior_hash=digest(prior_root/'summary.json');reused=load(prior_root,'summary.json')
        need(type(reused.get('windows')) is list and 1<=len(reused['windows'])<=43200,'Invalid prior window roster')
        for i,w in enumerate(reused['windows'],1):
            name=f'window_{i:05d}';need(w['window']==name,'Invalid prior window name');p=prior_root/name/'candidates.json';need(p.is_file() and not p.is_symlink() and p.resolve().is_relative_to(prior_root.resolve()) and 0<p.stat().st_size<=64*1024**2,'Invalid prior window');prior_files[name]=digest(p)
        audit(source,prior_root)
        need(digest(prior_root/'summary.json')==prior_hash and reused['source_sha256']==h and reused['tables']==list(tables),'Prior source or tables mismatch')
        banks=reused['bank_sha256']
    def cancel():
        if cancel_file is not None and Path(cancel_file).exists():raise Cancelled('Cancelled at safe checkpoint')
    def notify(**row):
        if progress is not None:progress(row)
    cancel()
    with tempfile.TemporaryDirectory(prefix='.plo27-',dir=out.parent) as tmp, ExitStack() as stack:
        stage=Path(tmp)/'result';stage.mkdir();ranker=None
        if rank:
            from plo5_rank_worker import RankWorker
            from plo5_rank_lru import CachedRankWorker
            ranker=CachedRankWorker(stack.enter_context(RankWorker(rank)))
        if reused is not None:
            parts=[(w['start'],w['seconds']) for w in reused['windows']];money=seat=None
        else:
            if session is None:
                start=0 if start is None else start;n=duration-start if seconds is None else seconds;need(type(start) is int and type(n) is int and 0<=start<duration and 2<=n<=duration-start,'Invalid interval')
                def coarse_progress(w):cancel();notify(phase='recognition',**w)
                scan_session(source,stage/'recognition',start,n,chunk=min(120,max(2,chunk)),workers=workers,backend=backend,ppp=ppp,suprema=suprema,progress=coarse_progress);session=stage/'recognition'/'session.json'
            index=read(session);need(index.get('source_sha256')==h and index.get('windows'),'Session source mismatch');first=index['windows'][0]['start'];end=index['windows'][-1]['start']+index['windows'][-1]['seconds'];start=first if start is None else start;n=end-start if seconds is None else seconds
            need(type(start) is int and type(n) is int and first<=start<end and 2<=n<=end-start,'Interval outside session');parts=list(windows(start,n,chunk));money=stack.enter_context(FastMoneyReader(workers=workers,backend=backend));card=MixedCardReader(ppp,suprema);seat_opts={}
            if seat_backend=='native':
                from plo5_native_seats import NativeSeatPool
                decoder=NativeSeatPool(workers);stack.callback(decoder.close);seat_opts['decoder']=decoder
            seat=SharedSeatReader(workers=workers,**seat_opts);stack.callback(seat.close)
        streams={t:ReconstructionStream(t) for t in tables};display_transitions=DisplayTransitions()
        for i,(a,length) in enumerate(parts,1):
            cancel();begin=perf_counter();d=stage/f'window_{i:05d}';d.mkdir();timing={};t=perf_counter()
            if reused is not None:
                from plo5_acceptance import load
                p=prior_root/d.name/'candidates.json';need(digest(p)==prior_files[d.name],'Prior observations changed');saved=load(prior_root,d.name+'/candidates.json');need(digest(p)==prior_files[d.name],'Prior observations changed');obs=saved['observations'];refined=saved['refinement'];coarse_count=reused['windows'][i-1]['coarse_frames'];need(obs['source_sha256']==h and len(frame_index(obs))==reused['windows'][i-1]['decoded_frames'],'Prior observation scope mismatch');timing['refinement']=0.0;timing['observation']=perf_counter()-t
            else:
                coarse=load_interval(session,a,length);coarse_count=len(coarse['frames']);refined=refine(source,coarse,a,length,card,budget=refine_budget) if refine_budget else None;timing['refinement']=perf_counter()-t;cancel();t=perf_counter()
                obs=observe_shared(source,coarse,refined,tables,money,card,seat,dealt,cancel=cancel);timing['observation']=perf_counter()-t;del coarse
            t=perf_counter();records=[];hands=[];metrics=[];models=[];continuations=[];counters={};anchors={};active_tables=[]
            for table in sorted(tables):
                cancel();m=table_manifest(obs,table);r=streams[table].feed(m,final=i==len(parts));anchors.update({f['pts']:f for f in r['anchor_frames']});active_tables.extend([table] if r['active_hand'] else []);ids={h['seed']['hand_id'] for h in r['hands']};need(not used&ids,'Duplicate candidate hand identity');used.update(ids)
                terminal=terminal_review(r,{k:v for k,v in cfg['terminal'].items() if k in ids},selected,rank_worker=ranker);models.extend(terminal['estimates']);cancel();continuations.extend(continuation_review(r,{k:v for k,v in cfg['bounds'].items() if k in ids},selected,rank_worker=ranker)['estimates']);metrics.extend(cfr_review(r,cfg['cfr'],selected,cache,native=native,rank=ranker,cancel=cancel));records.extend(r['decision_records']);hands.extend(r['hands']);counters[str(table)]=r['counts']
            timing['reconstruction_math']=perf_counter()-t;t=perf_counter();selection=select(records,selected);need(not selection['errors'] and not selection['adequate_count'],'Unexpected verified result from candidate path');cancel()
            current_pts={f['pts'] for f in obs['frames']};carried=[f for p,f in anchors.items() if p not in current_pts];carried.sort(key=lambda f:Fraction(f['pts']))
            evidence=dict(obs,frames=carried+obs['frames']);frame_index(evidence)
            cap=capture(source,evidence,records,d/'capture',selected);report=build(records,d/'study',selected,prints=d/'capture'/'manifest.json');timing['capture_report']=perf_counter()-t
            write_json(d/'candidates.json',dict(observations=obs,display_transitions=display_transitions.feed(obs),carried_anchors=carried,active_tables=active_tables,hands=hands,decision_contract=dict(version=VERSION,decisions=records),metrics=metrics,terminal_models=models,continuation_models=continuations,table_counts=counters,refinement=refined,strategic_certification=False))
            row=dict(window=d.name,start=a,seconds=length,coarse_frames=coarse_count,refined_frames=len(refined['frames']) if refined else 0,decoded_frames=len(obs['frames']),table_observations=sum(len(f['cards']) for f in obs['frames']),candidate_hands=len(hands),candidate_decisions=len(records),selected_pending=report['unresolved'],errors=report['errors'],prints=cap['unique_crops'],wall_seconds=perf_counter()-begin,stage_seconds=timing);rows.append(row)
            for k in ('coarse_frames','refined_frames','decoded_frames','table_observations','candidate_hands','candidate_decisions','selected_pending','errors','prints'):counts[k]+=row[k]
            notify(phase='reconstruction',completed=i,total=len(parts),**row);del obs,refined,records,hands,metrics,models,continuations,evidence,carried,anchors
        cancel();need(digest(source)==h and all(digest(v)==banks[k] for k,v in [('pppoker',ppp),('suprema',suprema)] if v),'Source or bank changed')
        if reused is not None:need(digest(prior_root/'summary.json')==prior_hash and all(digest(prior_root/name/'candidates.json')==sha for name,sha in prior_files.items()),'Prior input changed')
        summary=dict(version='plo5-integrated-candidate-v1',source_sha256=h,bank_sha256=banks,streets=list(selected),tables=list(tables),windows=rows,counts=dict(counts),unused_config_hands=sorted((set(cfg['terminal'])|set(cfg['cfr'])|set(cfg['bounds']))-used),money_backend=reused['money_backend'] if reused else backend,seat_backend=reused['seat_backend'] if reused else seat_backend,money_cache=money.cache.stats() if money else None,seat_cache=seat.stats() if seat else None,rank_cache=ranker.stats() if ranker else None,wall_seconds=perf_counter()-t0,window_boundaries_split_hands=False,observations_reused=reused is not None,prior_summary_sha256=prior_hash,beta_ready=False,strategy_verified=False,drivehud_beta=False)
        write_json(stage/'summary.json',summary)
        page=['<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>PLO Trainee</title><style>body{font:16px system-ui;max-width:860px;margin:auto;padding:24px}section{border:1px solid #ddd;padding:16px;border-radius:8px;margin:12px 0}</style><h1>PLO Trainee — revisão offline PLO5</h1><p><strong>Candidato experimental, não beta validado.</strong> Não há certificação automática de estratégia; zero erros não significa jogo correto. O estado candidato continua entre janelas; lacunas, conflitos e limites de segurança ainda interrompem mãos. As decisões aparecem na janela de encerramento do candidato. DriveHUD em standby.</p>']
        for r in rows:page.append(f'<section><h2>{r["start"]}–{r["start"]+r["seconds"]} s</h2><p>Decisões candidatas: {r["candidate_decisions"]}; pendentes selecionadas: {r["selected_pending"]}; erros demonstrados: {r["errors"]}</p><a href="{r["window"]}/study/index.html">Relatório seletivo</a> · <a href="{r["window"]}/candidates.json">Diagnóstico técnico</a></section>')
        page.append('<p><a href="summary.json">Resumo técnico</a></p></html>');(stage/'index.html').write_text(''.join(page),encoding='utf-8');need(not out.exists() and not out.is_symlink(),'Output appeared');os.rename(stage,out)
    return summary


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('video');p.add_argument('output');p.add_argument('--session');p.add_argument('--observations-from');p.add_argument('--start',type=int);p.add_argument('--seconds',type=int);p.add_argument('--chunk',type=int,default=20);p.add_argument('--tables',type=int,nargs='+',default=[1,2,3,4]);p.add_argument('--streets',nargs='+',choices=STREETS,default=list(STREETS));p.add_argument('--workers',type=int,choices=(1,2,3),default=2);p.add_argument('--backend',choices=('cli','native'),default='cli');p.add_argument('--seat-backend',choices=('cli','native'),default='cli');p.add_argument('--ppp');p.add_argument('--suprema');p.add_argument('--refine-budget',type=int,default=8);p.add_argument('--configs');p.add_argument('--cache');p.add_argument('--native');p.add_argument('--rank');p.add_argument('--cancel-file');a=p.parse_args(argv)
    try:r=run(a.video,a.output,start=a.start,seconds=a.seconds,session=a.session,chunk=a.chunk,tables=a.tables,streets=a.streets,workers=a.workers,backend=a.backend,seat_backend=a.seat_backend,ppp=a.ppp,suprema=a.suprema,refine_budget=a.refine_budget,configs=read(a.configs) if a.configs else None,cache=a.cache,native=a.native,rank=a.rank,cancel_file=a.cancel_file,observations_from=a.observations_from,progress=lambda w:print(json.dumps(dict(progress=w),ensure_ascii=False),flush=True))
    except Cancelled:print('Cancelado em checkpoint seguro.',flush=True);return 2
    print(json.dumps(r,ensure_ascii=False),flush=True);return 0

if __name__=='__main__':raise SystemExit(main())
