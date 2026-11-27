"""Offline PLO5 text batch intake and common decision contract.
Supported grammar: strict PokerStars-style USD cash exports, not native DriveHUD DB.
"""
import argparse
import hashlib
import json
from pathlib import Path
from plo5_history_intake import START, HEADER, DEALT
from plo5_history_replay import reconstruct, HEADER as FULL_HEADER, money
from plo5_pre_gto_context import need, cards
from plo5_selective_review import select, street_filter, STREETS, action_key, VERSION
from plo5_snapshot_replay import reveal
from plo5_decision_math import evaluate_model
import plo5_pre_gto_tree as pre
import plo5_post_gto_tree as post

LIMIT = 16*1024**2


def load(paths):
    need(type(paths) is list and 1<=len(paths)<=32,'Select 1–32 local TXT files')
    entries={}; conflicts=set(); rejected=[]; sources=[]; duplicates=0; count=0; size=0
    for name in paths:
        p=Path(name);need(p.is_file() and not p.is_symlink() and p.suffix.lower()=='.txt' and 0<p.stat().st_size<=LIMIT,'Local TXT required')
        raw=p.read_bytes();size+=len(raw);need(size<=4*LIMIT,'Total input budget exceeded')
        source=hashlib.sha256(raw).hexdigest();sources.append(source)
        try:s=raw.decode('utf-8-sig').replace('\r\n','\n')
        except UnicodeError:rejected.append(dict(source=source,reason='UNSUPPORTED_ENCODING'));continue
        offsets=[m.start() for m in START.finditer(s)]
        if not offsets or s[:offsets[0]].strip():rejected.append(dict(source=source,reason='UNSUPPORTED_FORMAT'));continue
        for a,b in zip(offsets,offsets[1:]+[len(s)]):
            count+=1;need(count<=10000,'Hand budget exceeded');hand=s[a:b].strip();head=hand.splitlines()[0];m=HEADER.match(head)
            if not m or 'Tournament' in head:rejected.append(dict(source=source,reason='UNSUPPORTED_VARIANT'));continue
            ident=m.group(1);digest=hashlib.sha256(hand.encode()).hexdigest()
            if ident in entries:
                if entries[ident]['sha256']==digest:duplicates+=1
                else:conflicts.add(ident)
                continue
            entries[ident]=dict(sha256=digest,source=source,raw=hand,id=ident)
    records=[]
    for ident,e in entries.items():
        if ident in conflicts:rejected.append(dict(hand_id=ident,reason='CONFLICTING_HAND_ID'));continue
        found=DEALT.findall(e['raw'])
        if len(found)!=1:rejected.append(dict(hand_id=ident,reason='MISSING_OR_MULTIPLE_HERO'));continue
        try:h=cards(found[0][1].split());record=dict(e,hero=found[0][0],holding=h);r=reconstruct(record)
        except ValueError as exc:rejected.append(dict(hand_id=ident,reason=str(exc)));continue
        records.append((record,r))
    return records,dict(sources=sources,duplicates=duplicates,conflicts=len(conflicts),rejected=rejected,records_seen=count)


def decisions(record,r,streets=STREETS,*,config=None,cache=None,cfr_executable=None,rank_worker=None):
    selected=street_filter(streets);bb=r['bb_cents'];sb=money(FULL_HEADER.fullmatch(record['raw'].splitlines()[0])[2]);s=pre.start(r['stacks_cents'],sb,bb);root=s;prior=None;prefix=[];rows=[];metrics=[];estimates=[]
    if config is not None:
        need(type(config) is dict and {'ranges','rake_bps','rake_cap','rake_on_fold'}<=set(config)<={'ranges','rake_bps','rake_cap','rake_on_fold','iterations','pot_bps','joint'},'Invalid model config');need(cache is not None,'Cache required')
    for j,e in enumerate(r['events']):
        if 'cards' in e:
            was_pre=isinstance(s,pre.State);s=reveal(s,e['cards']);root=s
            if was_pre and config is not None and len(s.active)==len(s.order) and all(s.remaining) and len(set(s.total_paid))==1 and s.actor==s.order[0]:
                prior=dict(variant=5,board=list(s.board),seats=list(s.order),actor=s.actor,pot=s.pot,bb=bb,stacks=dict(zip(s.order,s.remaining)),ranges=config['ranges'],rake_bps=config['rake_bps'],rake_cap=config['rake_cap'],tree_version=post.VERSION,continuation_version='text-flop-prior-v1')
            elif prior is not None:prefix.append(['chance',e['cards'][0],0])
            continue
        engine=pre if isinstance(s,pre.State) else post;board=[] if engine is pre else list(s.board);street={0:'preflop',3:'flop',4:'turn',5:'river'}[len(board)]
        if e['position']==r['hero_position']:
            b=engine.bounds(s);i=s.pending[0];call=b['call_payment'];odds=call/(s.pot+call) if call else None
            d=dict(hand_id=record['id'],decision_id=str(j),street=street,action=action_key([e['action'],e['amount']]),pot_odds=odds,reconstruction_verified=False,strategy_verified=False,action_set_complete=False,action_ev_bounds={},evidence=None);rows.append(d)
            if street in selected:
                metrics.append(dict(hand_id=record['id'],decision_id=str(j),street=street,position=s.actor,board=board,holding=record['holding'],pot_bb=s.pot/bb,call_bb=call/bb,pot_odds_gross=odds,effective_remaining_bb_by_opponent={s.order[k]:min(s.remaining[i],s.remaining[k])/bb for k in s.active if k!=i},hu_spr_street_start=min(root.remaining)/root.pot if len(root.order)==2 and root.pot else None,record_sha256=record['sha256'],source_sha256=record['source']))
                if config is not None:
                    result=dict(hand_id=record['id'],decision_id=str(j),status='NO_SUPPORTED_POSTFLOP_ROOT')
                    if prior is not None:
                        m=dict(context=prior,history=list(prefix),holding=record['holding'],action=[e['action'],e['amount']],**{k:v for k,v in config.items() if k in ('rake_on_fold','iterations','pot_bps','joint')})
                        try:a=evaluate_model(cache,m,cfr_executable=cfr_executable,rank_worker=rank_worker)
                        except ValueError as exc:result.update(status='MODEL_UNAVAILABLE',reason=str(exc))
                        else:result.update(status='EXPERIMENTAL_MODEL_ONLY',estimate=a)
                    estimates.append(result)
        s=engine.step(s,e['position'],e['action'],e['amount'])
        if prior is not None:prefix.append([e['position'],e['action'],e['amount']])
    return rows,metrics,estimates


def batch(paths,streets=STREETS,*,configs=None,cache=None,cfr_executable=None,rank_worker=None):
    selected=street_filter(streets);records,stats=load(paths);configs={} if configs is None else configs;need(type(configs) is dict and len(configs)<=64 and set(configs)<={x[0]['id'] for x in records},'Unknown model hand or config budget')
    rows=[];metrics=[];estimates=[]
    for record,r in records:
        a,b,c=decisions(record,r,selected,config=configs.get(record['id']),cache=cache,cfr_executable=cfr_executable,rank_worker=rank_worker);rows.extend(a);metrics.extend(b);estimates.extend(c);need(len(rows)<=10000,'Decision budget exceeded; split files')
    return dict(version='plo5-text-batch-v1',format='POKERSTARS_STYLE_USD_PLO5',intake=stats,consistent_hands=len(records),decision_contract=dict(version=VERSION,decisions=rows),metrics=metrics,experimental_estimates=estimates,selection=select(rows,selected),source_truth_verified=False,drivehud_format_verified=False)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output');p.add_argument('sources',nargs='+');p.add_argument('--streets',nargs='+',choices=STREETS,default=list(STREETS));p.add_argument('--configs');p.add_argument('--cache');p.add_argument('--native');p.add_argument('--rank');a=p.parse_args(argv)
    out=Path(a.output);need(out.suffix=='.json' and not out.exists() and not out.is_symlink(),'New JSON required')
    configs=None
    if a.configs:
        c=Path(a.configs);need(c.is_file() and not c.is_symlink() and 0<c.stat().st_size<=LIMIT,'Invalid config file');configs=json.loads(c.read_text('utf-8'))
    opts=dict(configs=configs,cache=a.cache,cfr_executable=a.native)
    if a.rank:
        from plo5_rank_worker import RankWorker
        with RankWorker(a.rank) as w:r=batch(a.sources,a.streets,rank_worker=w,**opts)
    else:r=batch(a.sources,a.streets,**opts)
    with out.open('x',encoding='utf-8') as f:json.dump(r,f,ensure_ascii=False,allow_nan=False,indent=2)
    return 0

if __name__=='__main__':raise SystemExit(main())
