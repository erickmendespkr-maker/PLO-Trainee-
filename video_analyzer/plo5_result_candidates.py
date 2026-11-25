"""Offline PLO5 result-label candidates linked to audited hand draft frames."""
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
from plo5_context_candidates import read_roi, parse_amount

LABELS = {'showdown':'showdown','win':'payout','won':'payout','ganhou':'payout',
          'return':'return','returned':'return','devolucao':'return','devolução':'return',
          'rebuy':'rebuy','re-buy':'rebuy','recarga':'rebuy','top-up':'rebuy'}


def parse_result(text):
    """Exact visible labels; no payout inferred from balance, pot or showdown."""
    if not isinstance(text,str):
        return None
    parts=' '.join(text.lower().split()).split(' ',1)
    kind=LABELS.get(parts[0]); tail=parts[1] if len(parts)==2 else ''
    if kind is None or (kind=='showdown' and tail):
        return None
    pot=None
    if kind=='payout':
        m=re.match(r'^(main|principal|side [1-5]|lateral [1-5])(?: |$)',tail)
        if m:
            tag=m[1]; pot='main' if tag in ('main','principal') else 'side_'+tag[-1]
            tail=tail[m.end():]
    amount=parse_amount(tail) if tail else None
    if tail and (amount is None or amount['value']=='0'):
        return None
    return {'kind':kind,'pot_id_candidate':pot,'displayed_amount':amount}


def validate_profile(profile, regions):
    require(type(profile) is dict and set(profile)=={'variant','tables'} and type(profile['variant']) is int and profile['variant']==5,'PLO5 profile required')
    known={r['table_id']:r for r in regions}; tables=profile['tables']
    require(type(tables) is list and len(tables)==len(known),'One result profile per region')
    out={}
    for t in tables:
        require(type(t) is dict and set(t)=={'table_id','seats'},'Invalid result table')
        tid=t['table_id']; seats=t['seats']
        require(type(tid) is int and tid in known and tid not in out and type(seats) is list and 2<=len(seats)<=6,'Invalid table/seats')
        ids=set(); rects=[]
        for s in seats:
            require(type(s) is dict and set(s)=={'seat','result'} and type(s['seat']) is int and 1<=s['seat']<=6 and s['seat'] not in ids,'Invalid result seat')
            ids.add(s['seat']); rects.append(box(s['result'],known[tid]['width'],known[tid]['height']))
        require(not any(overlap(a,b) for i,a in enumerate(rects) for b in rects[:i]),'Overlapping result ROIs')
        out[tid]=t
    return out


def read_result(image, rect, threshold):
    roi=image.crop(box(rect,*image.size)); lo,hi=roi.convert('L').getextrema()
    if hi-lo<=12:
        return {'raw':'','candidate':None,'engine_confidence':None,'roi':rect,
                'roi_rgb_sha256':hashlib.sha256(roi.tobytes()).hexdigest(),'status':'uniform_blank_candidate','human_confirmed':False}
    r=read_roi(image,rect,'result',threshold)
    confidence=r['engine_confidence']
    parsed=parse_result(r['raw']) if confidence is not None and confidence>=threshold else None
    return {**r,'candidate':parsed,'status':'result_label_candidate' if parsed else 'uncertain_label'}


def bind_drafts(binding,manifest,drafts,tables):
    require(type(drafts) is dict and drafts.get('status')=='unverified_hand_timeline_drafts' and
            tuple(drafts.get(k) for k in ('job_id','variant','source_sha256','manifest_sha256'))==
            (binding['job_id'],5,binding['source_sha256'],binding['reports']['evidence/ingest/manifest.json']) and
            all(drafts.get(k) is False for k in ('hands_reconstructed','actions_verified','equity_ev_authorized','automatic_clip_selection_authorized')),'Draft identity/status mismatch')
    samples={s['file']:s for s in manifest['samples']}; links={}; ids=set()
    require(manifest['source_sha256']==binding['source_sha256'] and len(samples)==len(manifest['samples']),'Invalid manifest')
    def add(f,tid,draft_id):
        s=samples.get(f['file'])
        require(s is not None and s['table_id']==tid and f['pts']==s['actual_frame_timestamp_seconds'] and f['crop_sha256']==s['sha256'] and f['file'] not in links,'Draft frame mismatch')
        seats=[a['seat'] for a in f['actions']]
        require(len(seats)==len(set(seats)) and set(seats)=={x['seat'] for x in tables[tid]['seats']} and f['hero_seat_declared'] in seats,'Draft seat mismatch')
        links[f['file']]={'draft_id':draft_id,'hero_seat_declared':f['hero_seat_declared']}
    for d in drafts['drafts']:
        did=d['draft_id']; tid=d['table_id']; frames=d['frames']
        require(type(did) is str and re.fullmatch(r'table_[0-9]{2}_segment_[0-9]{4,}',did) and did not in ids and tid in tables and did.startswith(f'table_{tid:02d}_') and d['hand_id'] is None and d['complete_hand_verified'] is False and frames,'Invalid draft segment')
        ids.add(did)
        pts=[f['pts'] for f in frames]
        require(pts==sorted(set(pts)),'Invalid draft timeline')
        for f in frames: add(f,tid,did)
    for f in drafts['unassigned']: add(f,f['table_id'],None)
    require(set(links)==set(samples),'Draft coverage mismatch')
    return links


def episodes(rows, *, max_gap=10.):
    require(type(max_gap) in (int,float) and math.isfinite(max_gap) and 0<max_gap<=30,'Invalid gap')
    groups=defaultdict(list)
    for row in rows:
        groups[row['table_id'],row['seat']].append(row)
    out=[]
    for (tid,seat),items in sorted(groups.items()):
        counts=Counter(r['pts'] for r in items); prev=None; current=None
        for r in sorted(items,key=lambda r:r['pts']):
            p=r['pts']; reading=r['reading']; candidate=reading['candidate']; did=r['draft_id']
            if counts[p]>1 or did is None or reading['status']!='result_label_candidate' or candidate is None:
                prev=current=None; continue
            if current is not None and prev is not None and p-prev<=max_gap and current['draft_id']==did and current['candidate']==candidate:
                current['last_seen_pts']=p; current['evidence_files'].append(r['file'])
            else:
                current={'table_id':tid,'seat':seat,'draft_id':did,'candidate':candidate,'first_seen_pts':p,
                         'last_seen_pts':p,'evidence_files':[r['file']],'financial_event_verified':False,'status':'visible_result_episode_needs_review'}
                out.append(current)
            prev=p
    return sorted(out,key=lambda e:(e['table_id'],e['first_seen_pts'],e['seat']))


def analyze_job(database,job_id,draft_path,profile_path,*,threshold=.75,max_tasks=1024,max_gap=10.):
    require(type(threshold) in (int,float) and math.isfinite(threshold) and 0<=threshold<=1,'Invalid threshold')
    require(type(max_tasks) is int and 1<=max_tasks<=4096,'Invalid task budget')
    episodes([],max_gap=max_gap)
    binding=read_bound_evidence(database,job_id); job=OfflineJobStore(database).get(job_id)
    folder=Path(job['result_path']).parent/'evidence/ingest'
    def read(path,limit):
        p=Path(path); require(p.is_file() and not p.is_symlink() and 0<p.stat().st_size<=limit,'Unsafe JSON input')
        raw=p.read_bytes(); require(len(raw)<=limit,'Oversized JSON input')
        return json.loads(raw,object_pairs_hook=unique_pairs),hashlib.sha256(raw).hexdigest()
    drafts,dh=read(draft_path,32*1024*1024); profile,ph=read(profile_path,32768)
    manifest=read_manifest(folder/'manifest.json'); tables=validate_profile(profile,manifest['regions'])
    links=bind_drafts(binding,manifest,drafts,tables)
    tasks=sum(len(tables[s['table_id']]['seats']) for s in manifest['samples'])
    require(tasks<=max_tasks,'OCR task budget exceeded')
    rows=[]
    for s in manifest['samples']:
        data=(folder/s['file']).read_bytes(); require(hashlib.sha256(data).hexdigest()==s['sha256'],'Crop changed during OCR')
        with Image.open(io.BytesIO(data)) as im: image=im.convert('RGB')
        for seat in tables[s['table_id']]['seats']:
            rows.append({'table_id':s['table_id'],'seat':seat['seat'],'pts':s['actual_frame_timestamp_seconds'],'file':s['file'],
                         'crop_sha256':s['sha256'],**links[s['file']], 'reading':read_result(image,seat['result'],threshold)})
    result=episodes(rows,max_gap=max_gap)
    require(sha256(draft_path)==dh and sha256(profile_path)==ph and read_bound_evidence(database,job_id)==binding,'Inputs changed')
    return {'schema_version':1,'variant':5,'job_id':job_id,'source_sha256':binding['source_sha256'],
            'manifest_sha256':binding['reports']['evidence/ingest/manifest.json'],'draft_sha256':dh,'profile_sha256':ph,
            'status':'unverified_result_label_episodes','observations':rows,'episodes':result,'roi_tasks':tasks,
            'max_gap_seconds':max_gap,'threshold':threshold,'payouts_verified':False,'winners_verified':False,
            'financial_result_bb':None,'hands_reconstructed':False,'equity_ev_authorized':False,'automatic_clip_selection_authorized':False}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('database','job_id','drafts','profile','output'): p.add_argument(name)
    p.add_argument('--threshold',type=float,default=.75);p.add_argument('--max-tasks',type=int,default=1024);p.add_argument('--max-gap',type=float,default=10.)
    a=p.parse_args(argv); target=Path(a.output)
    require(target.suffix=='.json' and not target.exists() and not target.is_symlink(),'New JSON required')
    r=analyze_job(a.database,a.job_id,a.drafts,a.profile,threshold=a.threshold,max_tasks=a.max_tasks,max_gap=a.max_gap)
    with target.open('x',encoding='utf-8') as f: json.dump(r,f,indent=2,allow_nan=False)
    return 0


if __name__=='__main__': raise SystemExit(main())
