"""Fuse audited PLO5 candidate reports into review-only timeline segments."""
import argparse
from collections import defaultdict, Counter
import json
import math
from pathlib import Path

from offline_jobs import OfflineJobStore
from offline_ingest_pts_audit import read_manifest
from offline_video_ingest_probe import require
from plo5_ingest_job import read_bound_evidence
from plo5_card_candidates import analyze_job as cards_job, RANKS, SUITS
from plo5_context_candidates import analyze_job as context_job
from plo5_action_candidates import analyze_job as actions_job
from plo5_boundary_candidates import analyze_job as boundaries_job


def build_drafts(binding, manifest, cards, context, actions, boundaries, *, max_gap=10.):
    """Internal fusion of freshly generated reports; no imported assertions trusted as facts."""
    require(type(max_gap) in (int,float) and math.isfinite(max_gap) and 0<max_gap<=30,'Invalid gap')
    expected=(binding['job_id'],5,binding['source_sha256'],binding['reports']['evidence/ingest/manifest.json'])
    reports=(cards,context,actions,boundaries)
    statuses=('unverified_calibrated_card_candidates','unverified_position_and_money_candidates',
              'unverified_action_label_episodes','unverified_table_presence_and_board_reset_candidates')
    for report,status in zip(reports,statuses):
        require(tuple(report[k] for k in ('job_id','variant','source_sha256','manifest_sha256'))==expected
                and report['status']==status and report['equity_ev_authorized'] is False
                and report['hands_reconstructed'] is False,'Report identity/status mismatch')
    samples={s['file']:s for s in manifest['samples']}
    require(len(samples)==len(manifest['samples']) and manifest['source_sha256']==expected[2],'Invalid manifest')
    def index(report, multiple=False):
        out=defaultdict(list)
        for r in report['observations']:
            s=samples.get(r['file'])
            require(s is not None and r['table_id']==s['table_id'] and r['pts']==s['actual_frame_timestamp_seconds']
                    and r['crop_sha256']==s['sha256'],'Observation not bound to crop')
            out[r['file']].append(r)
        require(set(out)==set(samples) and (multiple or all(len(v)==1 for v in out.values())), 'Incomplete/duplicate observations')
        return out
    ci,mi,ai,bi=(index(r,r is actions) for r in reports)
    cuts=defaultdict(list)
    for report,key in ((cards,'change_hints'),(boundaries,'candidates')):
        for h in report[key]:
            lo,hi=h['interval_pts']; tid=h['table_id']
            refs=[samples.get(f) for f in h['evidence_files']]
            require(lo<hi and h['hand_boundary_verified'] is False and all(s and s['table_id']==tid for s in refs)
                    and {lo,hi}<= {s['actual_frame_timestamp_seconds'] for s in refs},'Invalid boundary hint')
            cuts[tid].append((lo,hi))
    groups=defaultdict(list)
    for name,s in samples.items():
        c,m,b=ci[name][0],mi[name][0],bi[name][0]
        a=ai[name]; seats=[x['seat'] for x in a]; hero=m['hero_seat_declared']
        require(len(seats)==len(set(seats)) and set(seats)=={x['seat'] for x in m['seats']}
                and hero in seats and all(x['hero_seat_declared']==hero for x in a),'Seat profile mismatch')
        h,board=c['hero_cards'],c['board_cards']
        for values,counts in ((h,(5,)),(board,(0,3,4,5))):
            require(values is None or (type(values) is list and len(values) in counts and len(set(values))==len(values)
                    and all(type(v) is str and len(v)==2 and v[0] in RANKS and v[1] in SUITS for v in values)), 'Invalid card candidate')
        require(h is None or board is None or not set(h)&set(board),'Cross-field duplicate')
        groups[s['table_id']].append({'file':name,'pts':c['pts'],'crop_sha256':s['sha256'],'visible':b['visible'],
            'hero_seat_declared':hero,'hero_cards':h,'board':board,'context':m['derived_candidates'],
            'actions':[{'seat':x['seat'],'reading':x['reading'],'same_frame_context':x['same_frame_context']} for x in a]})
    drafts=[]; unassigned=[]
    for tid,rows in sorted(groups.items()):
        counts=Counter(r['pts'] for r in rows); current=None; prev=None; known=None; last_board=None; folded=False
        for r in sorted(rows,key=lambda x:x['pts']):
            pts=r['pts']; h=r['hero_cards']; board=r['board']
            inside=any(lo<pts<hi for lo,hi in cuts[tid])
            if counts[pts]>1 or not r['visible'] or inside:
                unassigned.append({'table_id':tid,**r,'reason':'duplicate_pts_or_absent_or_boundary_interior'})
                current=prev=known=last_board=None; folded=False; continue
            boundary=prev is not None and any(prev<=lo<hi<=pts for lo,hi in cuts[tid])
            conflict=(known is not None and h is not None and set(h)!=known) or (last_board is not None and board is not None and board[:len(last_board)]!=last_board)
            if current is None or boundary or pts-prev>max_gap or conflict:
                reason='candidate_boundary' if boundary else 'card_or_board_conflict' if conflict else 'first_or_discontinuous_observation'
                current={'draft_id':f'table_{tid:02d}_segment_{len(drafts)+1:04d}','table_id':tid,'start_reason':reason,
                         'hand_id':None,'hero_identity_verified':False,'frames':[],'complete_hand_verified':False}
                drafts.append(current); known=last_board=None; folded=False
            if h is not None: known=set(h)
            if board is not None: last_board=board
            street={0:'board_empty_candidate',3:'flop_candidate',4:'turn_candidate',5:'river_candidate'}.get(len(board)) if board is not None else None
            if h is not None and board==[]:
                current['hero_seat_candidate']=r['hero_seat_declared']
            hero_fold=any(x['seat']==r['hero_seat_declared'] and (x['reading'].get('candidate') or {}).get('action')=='fold' for x in r['actions'])
            current['frames'].append({**r,'street_candidate':street,'after_hero_fold_label':folded,'hero_fold_label':hero_fold})
            folded=folded or hero_fold; prev=pts
    return {'schema_version':1,'variant':5,'job_id':expected[0],'source_sha256':expected[2],'manifest_sha256':expected[3],
            'status':'unverified_hand_timeline_drafts','drafts':drafts,'unassigned':unassigned,
            'hands_reconstructed':False,'actions_verified':False,'equity_ev_authorized':False,'automatic_clip_selection_authorized':False}


def analyze_job(database,job_id,card_profile,templates,context_profile,action_profile,calibration,*,max_gap=10.,max_tasks=1024):
    binding=read_bound_evidence(database,job_id)
    job=OfflineJobStore(database).get(job_id)
    manifest=read_manifest(Path(job['result_path']).parent/'evidence/ingest/manifest.json')
    cards=cards_job(database,job_id,card_profile,templates,max_gap=max_gap)
    context=context_job(database,job_id,context_profile,max_tasks=max_tasks)
    actions=actions_job(database,job_id,action_profile,max_gap=max_gap,max_tasks=max_tasks)
    boundaries=boundaries_job(database,job_id,calibration,max_gap=max_gap)
    result=build_drafts(binding,manifest,cards,context,actions,boundaries,max_gap=max_gap)
    require(read_bound_evidence(database,job_id)==binding,'Evidence changed')
    result['source_profiles']={k:r.get('profile_sha256',r.get('calibration_sha256')) for k,r in zip(('cards','context','actions','boundaries'),(cards,context,actions,boundaries))}
    result['template_sha256s']=cards['template_sha256s']
    return result


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('database','job_id','card_profile','templates','context_profile','action_profile','calibration','output'): p.add_argument(name)
    p.add_argument('--max-gap',type=float,default=10.); p.add_argument('--max-tasks',type=int,default=1024)
    a=p.parse_args(argv); target=Path(a.output)
    require(target.suffix=='.json' and not target.exists() and not target.is_symlink(),'New JSON required')
    result=analyze_job(a.database,a.job_id,a.card_profile,a.templates,a.context_profile,a.action_profile,a.calibration,max_gap=a.max_gap,max_tasks=a.max_tasks)
    with target.open('x',encoding='utf-8') as f: json.dump(result,f,indent=2,allow_nan=False)
    return 0


if __name__=='__main__':
    raise SystemExit(main())
