"""Offline PLO5 action-label episodes on audited crops, not confirmed actions."""
import argparse
from collections import Counter, defaultdict
import hashlib
import io
import json
import math
from pathlib import Path
import re

from PIL import Image
from offline_jobs import OfflineJobStore
from offline_ingest_pts_audit import read_manifest, unique_pairs
from offline_video_ingest_probe import sha256, require
from plo5_ingest_job import read_bound_evidence
from plo5_card_candidates import box, overlap
from plo5_context_candidates import validate_profile as validate_context, read_roi, parse_amount, as_bb

LABELS = {'fold':'fold','desistir':'fold','desistiu':'fold',
          'check':'check','mesa':'check','passou':'check',
          'call':'call','pagar':'call','pagou':'call',
          'bet':'bet','apostar':'bet','apostou':'bet',
          'raise':'raise','aumentar':'raise','aumentou':'raise',
          'all-in':'all_in','all in':'all_in','allin':'all_in'}


def parse_action(text):
    """Exact labels only; optional explicit-unit amount is not contribution or call cost."""
    if not isinstance(text,str):
        return None
    text = ' '.join(text.strip().lower().split())
    for label in sorted(LABELS,key=len,reverse=True):
        if text == label:
            return {'action':LABELS[label],'displayed_amount':None}
        if text.startswith(label+' ') and LABELS[label] not in ('fold','check'):
            amount=parse_amount(text[len(label)+1:])
            if amount is not None and amount['value']!='0':
                return {'action':LABELS[label],'displayed_amount':amount}
    return None


def validate_profile(profile, regions):
    require(type(profile) is dict and set(profile)=={'variant','tables'} and type(profile['variant']) is int and profile['variant']==5,'PLO5 profile required')
    require(type(profile['tables']) is list,'Invalid tables')
    context=[]
    for t in profile['tables']:
        require(type(t) is dict and set(t)=={'table_id','hero_seat','pot','blinds','seats'} and type(t['seats']) is list,'Invalid action table')
        require(all(type(s) is dict and set(s)=={'seat','stack','bet','dealer','action'} for s in t['seats']),'Each seat needs action ROI')
        context.append(dict(t,seats=[{k:v for k,v in s.items() if k!='action'} for s in t['seats']]))
    validate_context({'variant':5,'tables':context},regions)
    known={r['table_id']:r for r in regions}
    for t in profile['tables']:
        r=known[t['table_id']]; size=(r['width'],r['height'])
        rects=[box(t[k],*size) for k in ('pot','blinds')]
        rects.extend(box(s[k],*size) for s in t['seats'] for k in ('stack','bet','dealer','action'))
        require(not any(overlap(a,b) for i,a in enumerate(rects) for b in rects[:i]),'Overlapping action/context ROIs')
    return {t['table_id']:t for t in profile['tables']}


def read_action(image,rect,threshold):
    gray=image.crop(box(rect,*image.size)).convert('L')
    lo,hi=gray.getextrema()
    if hi-lo<=12:
        roi=image.crop(box(rect,*image.size))
        return {'raw':'','engine_confidence':None,'roi':rect,'roi_rgb_sha256':hashlib.sha256(roi.tobytes()).hexdigest(),
                'candidate':None,'status':'uniform_blank_candidate','human_confirmed':False}
    # Reuse the existing OCR path; ignore its amount-only candidate for this field.
    result=read_roi(image,rect,'action',threshold)
    confidence=result['engine_confidence']
    candidate=parse_action(result['raw']) if confidence is not None and confidence>=threshold else None
    return {**result,'candidate':candidate,'status':'action_label_candidate' if candidate else 'uncertain_label'}


def episodes(rows, *, max_gap=10.):
    """Group repeated visible labels, retain uncertainty and do not count poker actions."""
    require(type(max_gap) in (int,float) and math.isfinite(max_gap) and 0<max_gap<=30,'Invalid max gap')
    groups=defaultdict(list)
    for row in rows:
        t,s,p=row['table_id'],row['seat'],row['pts']
        require(type(t) is int and 1<=t<=4 and type(s) is int and 1<=s<=6 and type(p) in (int,float) and math.isfinite(p),'Invalid observation')
        groups[t,s].append(row)
    output=[]; duplicates=0
    for (t,s),items in sorted(groups.items()):
        counts=Counter(r['pts'] for r in items)
        previous=None; current=None
        for row in sorted(items,key=lambda r:r['pts']):
            pts=row['pts']; label=row['reading']['candidate']
            status=row['reading']['status']
            if counts[pts]>1:
                duplicates+=1; previous=current=None; continue
            if previous is not None and pts-previous['pts']>max_gap:
                previous=current=None
            if status!='action_label_candidate' or label is None:
                current=None
                previous=row if status=='uniform_blank_candidate' else None
                continue
            action=label['action']
            if current is not None and current['action']==action:
                current['last_seen_pts']=pts
                current['evidence_files'].append(row['file'])
                current['observations']+=1
            else:
                current={'table_id':t,'seat':s,'action':action,'first_seen_pts':pts,'last_seen_pts':pts,
                         'onset_review_interval_pts':[previous['pts'],pts] if previous else None,
                         'evidence_files':[row['file']],'observations':1,
                         'status':'visible_label_episode_not_confirmed_action','order_verified':False,
                         'distinct_poker_action_verified':False}
                output.append(current)
            previous=row
    return sorted(output,key=lambda r:(r['table_id'],r['first_seen_pts'],r['seat'])),duplicates


def analyze_job(database,job_id,profile_path,*,threshold=.75,max_tasks=1024,max_gap=10.,cache_capacity=0):
    require(type(threshold) in (int,float) and math.isfinite(threshold) and 0<=threshold<=1,'Invalid OCR threshold')
    require(type(max_tasks) is int and 1<=max_tasks<=4096,'Invalid task budget')
    episodes([],max_gap=max_gap)
    require(type(cache_capacity) is int and 0<=cache_capacity<=2048,'Invalid action cache capacity')
    cache=None
    if cache_capacity:
        from plo5_action_cache import ActionCache
        cache=ActionCache(read_action,cache_capacity)
    action_reader=cache.read if cache is not None else read_action
    binding=read_bound_evidence(database,job_id)
    job=OfflineJobStore(database).get(job_id)
    folder=Path(job['result_path']).parent/'evidence/ingest'
    p=Path(profile_path)
    require(p.is_file() and not p.is_symlink() and 0<p.stat().st_size<=32768,'Unsafe action profile')
    raw=p.read_bytes(); profile=json.loads(raw,object_pairs_hook=unique_pairs)
    manifest=read_manifest(folder/'manifest.json'); tables=validate_profile(profile,manifest['regions'])
    budget=sum(2+3*len(tables[s['table_id']]['seats']) for s in manifest['samples'])
    require(budget<=max_tasks,'OCR task budget exceeded')
    observations=[]; tasks=0
    for s in manifest['samples']:
        data=(folder/s['file']).read_bytes()
        require(hashlib.sha256(data).hexdigest()==s['sha256'],'Crop changed during action OCR')
        with Image.open(io.BytesIO(data)) as im:
            image=im.convert('RGB')
        t=tables[s['table_id']]
        labels=[(seat,action_reader(image,seat['action'],threshold)) for seat in t['seats']]
        tasks+=len(labels)
        pot=blinds=None
        if any(r['candidate'] is not None for _,r in labels):
            pot,blinds=(read_roi(image,t[k],k,threshold) for k in ('pot','blinds')); tasks+=2
        for seat,reading in labels:
            context=None
            if reading['candidate'] is not None:
                stack,bet=(read_roi(image,seat[k],k,threshold) for k in ('stack','bet')); tasks+=2
                b=blinds['candidate']
                context={'pot':pot,'blinds':blinds,'stack':stack,'bet':bet,
                         'pot_bb':as_bb(pot['candidate'],b),'remaining_stack_bb':as_bb(stack['candidate'],b),
                         'visible_bet_bb':as_bb(bet['candidate'],b),
                         'label_amount_bb':as_bb(reading['candidate']['displayed_amount'],b),
                         'amount_to_call_bb':None,'incremental_contribution_bb':None}
            observations.append({'table_id':s['table_id'],'seat':seat['seat'],'hero_seat_declared':t['hero_seat'],
                                 'pts':s['actual_frame_timestamp_seconds'],'file':s['file'],'crop_sha256':s['sha256'],
                                 'reading':reading,'same_frame_context':context})
    labels,duplicates=episodes(observations,max_gap=max_gap)
    require(sha256(p)==hashlib.sha256(raw).hexdigest() and read_bound_evidence(database,job_id)==binding,'Inputs changed')
    return {'schema_version':1,'variant':5,'job_id':job_id,'source_sha256':binding['source_sha256'],
            'manifest_sha256':binding['reports']['evidence/ingest/manifest.json'],'profile_sha256':hashlib.sha256(raw).hexdigest(),
            'status':'unverified_action_label_episodes','observations':observations,'episodes':labels,
            'duplicate_pts_observations_excluded':duplicates,'roi_tasks':tasks,'worst_case_roi_tasks':budget,
            'threshold':threshold,'max_gap_seconds':max_gap,'action_cache':cache.stats() if cache is not None else None,'actions_verified':False,'order_verified':False,
            'hands_reconstructed':False,'equity_ev_authorized':False,'automatic_clip_selection_authorized':False}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('database','job_id','profile','output'):
        p.add_argument(name)
    p.add_argument('--threshold',type=float,default=.75); p.add_argument('--max-tasks',type=int,default=1024)
    p.add_argument('--max-gap',type=float,default=10.);p.add_argument('--cache-capacity',type=int,default=0)
    a=p.parse_args(argv); target=Path(a.output)
    require(target.suffix=='.json' and not target.exists() and not target.is_symlink(),'New JSON output required')
    result=analyze_job(a.database,a.job_id,a.profile,threshold=a.threshold,max_tasks=a.max_tasks,max_gap=a.max_gap,cache_capacity=a.cache_capacity)
    with target.open('x',encoding='utf-8') as f:
        json.dump(result,f,indent=2,allow_nan=False)
    return 0


if __name__=='__main__':
    raise SystemExit(main())
