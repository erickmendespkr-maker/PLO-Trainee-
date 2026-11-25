"""Conditional PLO5 Hero ledger; OCR candidates are never accounting entries."""
import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re

from offline_jobs import OfflineJobStore
from offline_ingest_pts_audit import read_manifest, unique_pairs
from offline_video_ingest_probe import require, sha256
from plo5_ingest_job import read_bound_evidence

KINDS = {'contribution','return','payout','rebuy','withdrawal'}


def money(value):
    require(type(value) is str and re.fullmatch(r'\d{1,9}(?:\.\d{1,6})?',value),'Invalid BB decimal')
    return Decimal(value)


def fmt(value):
    return format(value.normalize(),'f') if value else '0'


def reconcile(row, frames):
    """Explicit reviewed incremental entries only. Exact decimal conservation."""
    require(set(row)=={'draft_id','hero_seat','complete','reviewer','before','after','events'},'Invalid review fields')
    require(type(row['complete']) is bool and type(row['reviewer']) is str and len(row['reviewer'])<=100,'Invalid review declaration')
    require(type(row['hero_seat']) is int and 1<=row['hero_seat']<=6 and all(f['hero_seat_declared']==row['hero_seat'] for f in frames.values()),'Hero seat mismatch')
    def anchor(item):
        if item is None: return None
        require(type(item) is dict and set(item)=={'file','bb'} and item['file'] in frames,'Unbound balance')
        return frames[item['file']]['pts'],money(item['bb'])
    before,after=anchor(row['before']),anchor(row['after'])
    require(before is None or after is None or before[0]<after[0],'Invalid balance order')
    require(type(row['events']) is list and len(row['events'])<=512,'Invalid event list')
    totals={k:Decimal(0) for k in KINDS}; previous=None; running=before[1] if before else None
    flags=[]
    for event in row['events']:
        require(type(event) is dict and set(event)=={'file','kind','bb'} and event['file'] in frames and event['kind'] in KINDS,'Invalid or unbound event')
        pts=frames[event['file']]['pts']; kind=event['kind']; amount=money(event['bb'])
        require(amount>0 and (previous is None or pts>previous) and (before is None or pts>before[0]) and (after is None or pts<after[0]),'Duplicate, unordered or out-of-window event')
        previous=pts; totals[kind]+=amount
        if totals['return']>totals['contribution']: flags.append('returns_exceed_contributions')
        if running is not None:
            running+= -amount if kind in ('contribution','withdrawal') else amount
            if running<0: flags.append('negative_intermediate_balance')
    if not row['complete'] or not row['reviewer'].strip() or before is None or after is None:
        flags.append('incomplete_review_or_anchors')
    net=totals['payout']+totals['return']-totals['contribution']
    adjustment=totals['rebuy']-totals['withdrawal']
    residual=after[1]-before[1]-adjustment-net if before and after else None
    if residual is not None and residual!=0: flags.append('balance_mismatch')
    ok=not flags
    return {'draft_id':row['draft_id'],'status':'conditional_reconciled' if ok else 'unresolved',
            'reviewer':row['reviewer'],'review_flags':sorted(set(flags)),
            'submitted_totals_bb':{k:fmt(v) for k,v in sorted(totals.items())},
            'external_adjustment_bb':fmt(adjustment),'residual_bb':fmt(residual) if residual is not None else None,
            'conditional_net_bb':fmt(net) if ok else None,
            'conditional_loss_over_30bb':net<Decimal(-30) if ok else None,
            'financial_result_verified':False,'ev_loss_bb':None,'equity_ev_authorized':False,
            'automatic_clip_selection_authorized':False}


def build(binding,manifest,drafts,results,review,draft_sha,result_sha):
    identity=(binding['job_id'],5,binding['source_sha256'],binding['reports']['evidence/ingest/manifest.json'])
    for report,status in ((drafts,'unverified_hand_timeline_drafts'),(results,'unverified_result_label_episodes')):
        require(tuple(report.get(k) for k in ('job_id','variant','source_sha256','manifest_sha256'))==identity and report.get('status')==status and report.get('equity_ev_authorized') is False and report.get('hands_reconstructed') is False,'Report identity mismatch')
    require(results.get('draft_sha256')==draft_sha and results.get('financial_result_bb') is None and results.get('payouts_verified') is False,'Invalid result report')
    require(type(review) is dict and set(review)=={'variant','job_id','draft_sha256','result_sha256','reviews'} and review['variant']==5 and review['job_id']==identity[0] and review['draft_sha256']==draft_sha and review['result_sha256']==result_sha,'Review identity mismatch')
    samples={s['file']:s for s in manifest['samples']}; require(len(samples)==len(manifest['samples']) and manifest['source_sha256']==identity[2],'Invalid manifest')
    segments={}; seen=set()
    def verify_frame(f,tid):
        s=samples.get(f['file'])
        require(s is not None and f['file'] not in seen and s['table_id']==tid and s['sha256']==f['crop_sha256'] and s['actual_frame_timestamp_seconds']==f['pts'],'Draft evidence mismatch')
        seen.add(f['file'])
    for d in drafts['drafts']:
        did=d['draft_id']; tid=d['table_id']
        require(type(did) is str and did not in segments and d['hand_id'] is None and d['complete_hand_verified'] is False and d['frames'],'Invalid draft')
        for f in d['frames']: verify_frame(f,tid)
        pts=[f['pts'] for f in d['frames']]; require(pts==sorted(set(pts)),'Ambiguous draft order')
        segments[did]={f['file']:f for f in d['frames']}
    for f in drafts['unassigned']: verify_frame(f,f['table_id'])
    require(seen==set(samples),'Incomplete draft coverage')
    require(type(review['reviews']) is list and len(review['reviews'])<=len(segments),'Invalid review count')
    output=[]; used=set()
    for row in review['reviews']:
        did=row['draft_id']; require(did in segments and did not in used,'Unknown or duplicate review')
        used.add(did); output.append(reconcile(row,segments[did]))
    return {'schema_version':1,'variant':5,'job_id':identity[0],'source_sha256':identity[2],'manifest_sha256':identity[3],
            'draft_sha256':draft_sha,'result_sha256':result_sha,'status':'conditional_financial_review_not_video_verified',
            'reviews':output,'unreviewed_draft_ids':sorted(set(segments)-used),'financial_results_verified':False,
            'equity_ev_authorized':False,'automatic_clip_selection_authorized':False}


def analyze_job(database,job_id,draft_path,result_path,review_path):
    binding=read_bound_evidence(database,job_id); job=OfflineJobStore(database).get(job_id)
    manifest=read_manifest(Path(job['result_path']).parent/'evidence/ingest/manifest.json')
    def read(path):
        p=Path(path); require(p.is_file() and not p.is_symlink() and 0<p.stat().st_size<=32*1024*1024,'Unsafe input')
        raw=p.read_bytes(); require(len(raw)<=32*1024*1024,'Oversized input')
        return json.loads(raw,object_pairs_hook=unique_pairs),hashlib.sha256(raw).hexdigest()
    drafts,dh=read(draft_path); results,rh=read(result_path); review,vh=read(review_path)
    report=build(binding,manifest,drafts,results,review,dh,rh)
    require(sha256(draft_path)==dh and sha256(result_path)==rh and sha256(review_path)==vh and read_bound_evidence(database,job_id)==binding,'Inputs changed')
    report['review_sha256']=vh
    return report


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('database','job_id','drafts','results','review','output'): p.add_argument(name)
    a=p.parse_args(argv); target=Path(a.output)
    require(target.suffix=='.json' and not target.exists() and not target.is_symlink(),'New JSON required')
    report=analyze_job(a.database,a.job_id,a.drafts,a.results,a.review)
    with target.open('x',encoding='utf-8') as f: json.dump(report,f,indent=2,allow_nan=False)
    return 0


if __name__=='__main__': raise SystemExit(main())
