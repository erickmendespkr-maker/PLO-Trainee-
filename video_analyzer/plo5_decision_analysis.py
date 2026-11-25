"""Offline PLO5 reviewed decision bridge; no OCR candidate becomes a verified fact."""
import argparse
from collections import Counter
from contextlib import closing
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import sqlite3

import strategic_normalize as norm
import strategic_store as store
from offline_jobs import OfflineJobStore
from offline_ingest_pts_audit import read_manifest, unique_pairs
from offline_video_ingest_probe import require, sha256
from plo5_ingest_job import read_bound_evidence
from plo5_equity_store import lookup_descriptor, SHA256, SOURCE, LICENSE, RANKS
from plo5_ev_comparison import compare, action_key

# Exact reviewed SQLite snapshot from block 11. Alternate builds require review.
EQUITY_DB_SHA256 = 'bddf887d08b9bfaeb55ab55e287b3398c31cf51620dde2ce9986baf7aeddaa9a'
# Multiplicity labels, not an identity of the exact rank-to-suit assignment.
PARTITIONS = {(2,2,1):'ds',(2,1,1,1):'ss',(3,1,1):'3-suit',
              (3,2):'3+2',(4,1):'4-suit',(5,):'mono'}


def open_readonly(path, *, immutable=False):
    p=Path(path)
    require(p.is_file() and not p.is_symlink(),'Existing local database required')
    db=sqlite3.connect(p.resolve().as_uri()+'?mode=ro'+('&immutable=1' if immutable else ''),uri=True)
    db.execute('PRAGMA query_only=ON')
    return db


def descriptor_reference(db, context):
    if context['street']!='preflop':
        return {'status':'NOT_APPLICABLE_POSTFLOP','gto':False}
    hero=context['hero']
    hand='-'.join(sorted((c[0] for c in hero),key=RANKS.index))
    suits=PARTITIONS[tuple(sorted(Counter(c[1] for c in hero).values(),reverse=True))]
    metadata=dict(db.execute('SELECT key,value FROM metadata'))
    require(all(metadata.get(k)==v for k,v in {'variant':'5','kind':'equity_vs_one_random_opponent',
            'csv_sha256':SHA256,'source':SOURCE,'license':LICENSE,'schema_version':'1'}.items()),'Equity provenance mismatch')
    result=lookup_descriptor(db,hand,suits)
    return {**result,'hand':hand,'suits':suits,'source':SOURCE,'license':LICENSE,
            'attribution':'SolvePoker (solvepoker.app)','csv_sha256':SHA256,
            'exact_suit_match':False,'strategy_reference':False,'frequency':None,'ev_bb':None,
            'scope':'preflop_vs_one_uniform_random_opponent_descriptor_only'}


def strategic_reference(db, context):
    require(db.execute('PRAGMA user_version').fetchone()[0]==store.VERSION,'Unsupported strategic database version')
    sid,_=store.scenario_identity(5,context)
    # Current schema only supports synthetic fixtures. Fail closed even if a
    # tampered DB bypasses the constraint; never return fixture frequencies/EV.
    require(db.execute('SELECT 1 FROM records WHERE synthetic<>1 OR synthetic IS NULL LIMIT 1').fetchone() is None,
            'Real strategy importer not enabled')
    count=db.execute('SELECT count(*) FROM records WHERE scenario_id=? AND synthetic=1',(sid,)).fetchone()[0]
    return {'status':'NO_MATCH','scenario_id':sid,'synthetic_matches_excluded':count,
            'authorized_strategy_records':0,'frequency':None,'ev_bb':None,'gto':False,
            'reason':'real_strategy_import_disabled'}


def find_frames(binding,manifest,drafts,review):
    identity=(binding['job_id'],5,binding['source_sha256'],binding['reports']['evidence/ingest/manifest.json'])
    require(tuple(drafts.get(k) for k in ('job_id','variant','source_sha256','manifest_sha256'))==identity
            and drafts.get('status')=='unverified_hand_timeline_drafts'
            and all(drafts.get(k) is False for k in ('hands_reconstructed','actions_verified','equity_ev_authorized','automatic_clip_selection_authorized')),'Draft identity mismatch')
    samples={s['file']:s for s in manifest['samples']}
    require(len(samples)==len(manifest['samples']) and manifest['source_sha256']==identity[2],'Manifest mismatch')
    seen=set(); segments={}
    def check(f,tid):
        s=samples.get(f['file'])
        require(s is not None and f['file'] not in seen and s['table_id']==tid and s['sha256']==f['crop_sha256'] and s['actual_frame_timestamp_seconds']==f['pts'],'Frame evidence mismatch')
        seen.add(f['file'])
    for d in drafts['drafts']:
        did=d['draft_id']; tid=d['table_id']; frames=d['frames']
        require(did not in segments and d['hand_id'] is None and d['complete_hand_verified'] is False and frames,'Invalid segment')
        pts=[f['pts'] for f in frames]; require(pts==sorted(set(pts)),'Ambiguous segment order')
        for f in frames: check(f,tid)
        segments[did]={f['file']:f for f in frames}
    for f in drafts['unassigned']: check(f,f['table_id'])
    require(seen==set(samples),'Incomplete draft coverage')
    frames=segments.get(review['draft_id'],{})
    a,b=frames.get(review['context_file']),frames.get(review['action_file'])
    require(a is not None and b is not None and 0<b['pts']-a['pts']<=10,'Separate ordered context/action frames required')
    return a,b


def exact_context(raw):
    c=norm.normalize_scenario(5,raw)
    # Normalization rounds to eight decimals. Refuse precision loss here.
    for k in ('stack','pot','to_call','rake_cap'):
        require(Fraction(norm.number(raw[k]))/Fraction(norm.number(raw['bb_size']))==Fraction(c[k]),'Context precision loss')
    require(Fraction(norm.number(raw['rake_percent']))==Fraction(c['rake_percent']),'Rake precision loss')
    return c


def analyze_review(binding,manifest,drafts,review,draft_sha,equity_db,strategy_db,**options):
    require(type(review) is dict and set(review)=={'variant','job_id','draft_sha256','draft_id','context_file','action_file','reviewer','context','chosen_action','hypotheses'}
            and type(review['variant']) is int and review['variant']==5 and review['job_id']==binding['job_id'] and review['draft_sha256']==draft_sha
            and type(review['reviewer']) is str and 0<len(review['reviewer'].strip())<=100,'Explicit review identity required')
    a,b=find_frames(binding,manifest,drafts,review)
    c=exact_context(review['context']); chosen=action_key(review['chosen_action'])
    base={'variant':5,'job_id':binding['job_id'],'draft_id':review['draft_id'],'source_sha256':binding['source_sha256'],
          'manifest_sha256':binding['reports']['evidence/ingest/manifest.json'],'draft_sha256':draft_sha,
          'context_file':a['file'],'action_file':b['file'],'context_pts':a['pts'],'action_pts':b['pts'],
          'reviewer':review['reviewer'],'context':c,'chosen_action_declared':review['chosen_action'],
          'video_verified':False,'gto_solution':False,'strategic_error_established':False,
          'financial_result_bb':None,'ev_loss_bb':None,'automatic_clip_selection_authorized':False}
    reasons=[]
    if a['hero_seat_declared']!=b['hero_seat_declared'] or not a['visible'] or not b['visible'] or a['hero_fold_label'] or a['after_hero_fold_label'] or b['after_hero_fold_label']:
        reasons.append('hero_or_timeline_conflict')
    for f in (a,b):
        if f['hero_cards'] is None or sorted(f['hero_cards'])!=c['hero'] or f['board'] is None or sorted(f['board'][:3])+f['board'][3:]!=c['board']:
            reasons.append('cards_missing_or_conflicting')
    ctx=a['context']; hero=a['hero_seat_declared']; pos=ctx.get('hero_position_candidate')
    if pos=='BTN/SB': pos='SB'
    if pos=='EP': pos='UTG'
    stacks=ctx.get('remaining_stacks_bb',{})
    observed_stack=stacks.get(str(hero),stacks.get(hero))
    for actual,expected,reason in ((ctx.get('pot_bb'),c['pot'],'pot'),(observed_stack,c['stack'],'hero_stack')):
        if actual is None or Fraction(actual)!=Fraction(expected): reasons.append(reason+'_missing_or_conflicting')
    seats_a=[x['seat'] for x in a['actions']]; seats_b=[x['seat'] for x in b['actions']]
    if pos!=c['position'] or len(seats_a)!=c['players'] or len(seats_b)!=c['players'] or len(set(seats_a))!=len(seats_a) or set(seats_a)!=set(seats_b) or hero not in seats_a:
        reasons.append('position_or_seat_count_conflict')
    prior=[(x['reading'].get('candidate') or {}).get('action') for x in a['actions'] if x['seat']==hero]
    if prior!=[None]: reasons.append('context_frame_has_action_label')
    labels=[(x['reading'].get('candidate') or {}).get('action') for x in b['actions'] if x['seat']==hero]
    if labels!=[chosen[0]]: reasons.append('action_label_missing_or_conflicting')
    if reasons:
        return {**base,'status':'INSUFFICIENT_DATA','reasons':sorted(set(reasons)),
                'starting_equity':None,'strategic_reference':None,'conditional_model':None}
    reference=descriptor_reference(equity_db,c)
    strategy=strategic_reference(strategy_db,c)
    hypotheses=review['hypotheses']; model=None; reasons=[]
    require(type(hypotheses) is dict,'Hypotheses must be an object')
    if not hypotheses: reasons.append('no_declared_range_response_model')
    elif c['players']!=2: reasons.append('multiway_model_not_supported')
    else:
        opponent=next(seat for seat in seats_a if seat!=hero)
        opponent_stack=stacks.get(str(opponent),stacks.get(opponent))
        if opponent_stack is None:
            return {**base,'status':'INSUFFICIENT_DATA','reasons':['opponent_stack_missing'],
                    'starting_equity':reference,'strategic_reference':strategy,'conditional_model':None}
        for s in hypotheses.values():
            require(s['variant']==5 and sorted(s['hero'])==c['hero'] and sorted(s['board'][:3])+s['board'][3:]==c['board'],'Model cards/context mismatch')
            for v,k in ((s['pot'],'pot'),(s['hero_stack'],'stack'),(s['opponent_street']-s['hero_street'],'to_call'),(s['rake_cap'],'rake_cap')):
                require(Fraction(v,s['bb'])==Fraction(c[k]),'Model monetary context mismatch')
            require(type(s['bb']) is int and s['bb']>0 and (review['context']['amount_unit']=='BB' or Fraction(s['bb'])==Fraction(norm.number(review['context']['bb_size']))),'Model chip unit mismatch')
            require(Fraction(s['opponent_stack'],s['bb'])==Fraction(opponent_stack),'Model opponent stack mismatch')
            require(Fraction(s['rake_bps'],100)==Fraction(c['rake_percent']),'Model rake mismatch')
        model=compare(hypotheses,review['chosen_action'],**options)
    status='NO_MATCH'
    if model is not None:
        coverage=model['coverage']
        status='CONDITIONAL_MODEL_ONLY' if coverage['hypotheses_comparable'] else ('NO_MATCH' if coverage['no_match'] else 'INSUFFICIENT_DATA')
    return {**base,'status':status,'reasons':reasons,
            'starting_equity':reference,'strategic_reference':strategy,'conditional_model':model,
            'context_is_reviewed_declaration_not_verified':True}


def analyze_job(database,job_id,draft_path,review_path,equity_path,strategy_path,**options):
    binding=read_bound_evidence(database,job_id); job=OfflineJobStore(database).get(job_id)
    manifest=read_manifest(Path(job['result_path']).parent/'evidence/ingest/manifest.json')
    def read(path):
        p=Path(path); require(p.is_file() and not p.is_symlink() and 0<p.stat().st_size<=32*1024*1024,'Unsafe JSON')
        raw=p.read_bytes(); require(len(raw)<=32*1024*1024,'Oversized JSON')
        return json.loads(raw,object_pairs_hook=unique_pairs),hashlib.sha256(raw).hexdigest()
    drafts,dh=read(draft_path); review,rh=read(review_path)
    require(sha256(equity_path)==EQUITY_DB_SHA256,'Unreviewed equity snapshot')
    with closing(open_readonly(equity_path,immutable=True)) as edb, closing(open_readonly(strategy_path)) as sdb:
        sdb.execute('BEGIN')
        report=analyze_review(binding,manifest,drafts,review,dh,edb,sdb,**options)
    require(sha256(equity_path)==EQUITY_DB_SHA256 and sha256(draft_path)==dh and sha256(review_path)==rh and read_bound_evidence(database,job_id)==binding,'Inputs changed')
    return {**report,'review_sha256':rh,'equity_database_sha256':EQUITY_DB_SHA256}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for k in ('database','job_id','drafts','review','equity_db','strategy_db','output'): p.add_argument(k)
    a=p.parse_args(argv); out=Path(a.output)
    require(out.suffix=='.json' and not out.exists() and not out.is_symlink(),'New JSON output required')
    result=analyze_job(a.database,a.job_id,a.drafts,a.review,a.equity_db,a.strategy_db)
    with out.open('x',encoding='utf-8') as f: json.dump(result,f,indent=2,allow_nan=False)
    return 0


if __name__=='__main__': raise SystemExit(main())
