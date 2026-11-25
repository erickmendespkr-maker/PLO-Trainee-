"""Bounded offline PLO5 timeline candidates, not verified hand histories."""
import argparse
from collections import Counter, defaultdict
from fractions import Fraction
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile
from PIL import Image
from offline_jobs import OfflineJobStore
from offline_video_ingest_probe import sha256
from plo5_visual_calibration import load_job, checked_image, train, observe, LAYOUTS, RANKS, SUITS
from plo5_ingest_job import read_bound_evidence
from plo5_action_candidates import read_action, episodes
from plo5_session_export import load, write
from plo5_leak_review import need


def calibration(jobs):
    need(type(jobs) is list and 1<=len(jobs)<=8,'Invalid calibration jobs')
    training=[];snapshots={};parts={}
    for j in jobs:
        need(type(j) is dict and set(j)=={'database','job_id','annotations'},'Invalid job')
        b,folder,m=load_job(j['database'],j['job_id']);a,ah=load(j['annotations']);jid=b['job_id']
        need(jid not in snapshots and type(a['variant']) is int and a['variant']==5 and a['job_id']==jid and a['source_sha256']==b['source_sha256'] and a['manifest_sha256']==b['reports']['evidence/ingest/manifest.json'],'Training identity mismatch')
        ss={s['file']:s for s in m['samples']};seen=set();early=[];late=[]
        for r in a['rows']:
            s=ss.get(r['file']);p=r['partition'];v=r['truth']
            need(s and r['file'] not in seen and r['sha256']==s['sha256'] and p in ('train','holdout') and type(v.get('visible')) is bool,'Invalid training row')
            seen.add(r['file']);h=s['sha256'];need(h not in parts or parts[h]==p,'Training/holdout overlap');parts[h]=p
            (early if p=='train' else late).append(s['actual_frame_timestamp_seconds'])
            if p=='train' and v['visible']:
                cards=v.get('hero',[])+v.get('board',[]);need(len(cards)==len(set(cards)),'Duplicate training cards');training.append((checked_image(folder,s),v))
        need(early and late and max(early)<min(late),'Invalid chronological split');snapshots[jid]=(j,b,ah,max(early),m)
    bank=train(training);need(set(bank['rank'])==set(RANKS) and set(bank['suit'])==set(SUITS),'Incomplete template classes');return bank,snapshots


def command(args):
    p=subprocess.run(args,stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=90,check=True)
    need(len(p.stdout)<32*1024*1024 and len(p.stderr)<8*1024*1024,'Media output exceeds budget');return p


def extract(source,start,seconds,folder,size):
    need(type(start) is int and start>=0 and type(seconds) is int and 2<=seconds<=60,'Invalid dense window')
    probe=json.loads(command(['ffprobe','-v','error','-select_streams','v:0','-read_intervals',f'{start}%{start+seconds+1}','-show_entries','stream=time_base:frame=best_effort_timestamp','-of','json',str(source)]).stdout)
    tb=Fraction(probe['streams'][0]['time_base']);known={int(x['best_effort_timestamp']) for x in probe['frames'] if 'best_effort_timestamp' in x}
    p=command(['ffmpeg','-nostdin','-hide_banner','-loglevel','info','-threads','1','-filter_threads','1','-copyts','-ss',str(start),'-i',str(source),'-map','0:v:0','-vf',"select='isnan(prev_selected_t)+gt(floor(t),floor(prev_selected_t))',showinfo",'-frames:v',str(seconds),'-fps_mode','passthrough','-q:v','3','-an','-sn','-dn','-n',str(folder/'frame_%03d.jpg')])
    bases=re.findall(r'config in time_base: (\d+/\d+)',p.stderr);need(bases and all(Fraction(x)==tb for x in bases),'PTS time base mismatch')
    stamps=[int(x) for x in re.findall(r'\bn:\s*\d+\s+pts:\s*(-?\d+)\s+pts_time:',p.stderr)];files=sorted(folder.glob('frame_*.jpg'))
    need(len(files)==len(stamps)==seconds and all(x in known for x in stamps),'Missing or unbound PTS')
    need([math.floor(x*tb) for x in stamps]==list(range(start,start+seconds)),'Missing sampled second')
    out=[]
    for f,t in zip(files,stamps):
        with Image.open(f) as im:need(im.size==size,'Source geometry changed')
        out.append({'file':f.name,'sha256':sha256(f),'pts_ticks':t,'time_base':str(tb),'pts':float(t*tb)})
    return out


def timeline(rows,max_gap=2.5):
    need(type(max_gap) in (int,float) and math.isfinite(max_gap) and 0<max_gap<=5,'Invalid gap')
    groups=defaultdict(list);names=set()
    for r in rows:
        need(type(r['table_id']) is int and 1<=r['table_id']<=4 and type(r['pts']) in (int,float) and math.isfinite(r['pts']) and r['file'] not in names,'Invalid observation')
        names.add(r['file']);groups[r['table_id']].append(r)
    segments=[];unassigned=[]
    for tid,items in sorted(groups.items()):
        counts=Counter(r['pts'] for r in items);current=None;last=None;hero=None;board=None;folded=False
        for r in sorted(items,key=lambda x:x['pts']):
            t=r['pts'];h=r['hero_cards'];b=r['board_cards']
            if counts[t]>1 or r['visible'] is not True:
                unassigned.append({'file':r['file'],'table_id':tid,'reason':'duplicate_pts_or_visibility_uncertain'});current=last=hero=board=None;folded=False;continue
            for cards,allowed in ((h,(5,)),(b,(0,3,4,5))):
                need(cards is None or (type(cards) is list and len(cards) in allowed and len(set(cards))==len(cards) and all(type(c) is str and len(c)==2 and c[0] in RANKS and c[1] in SUITS for c in cards)),'Invalid cards')
            need(h is None or b is None or not set(h)&set(b),'Cross-field conflict')
            reason=None
            if current is None:reason='window_start_or_visibility_gap'
            elif t-last['pts']>max_gap:reason='sampling_gap'
            elif hero is not None and h is not None and set(h)!=hero:reason='private_cards_conflict'
            elif board is not None and b is not None and b[:len(board)]!=board:reason='board_reset_or_conflict'
            if reason:
                current={'segment_id':f't{tid}_{len(segments)+1:04d}','table_id':tid,'start_reason':reason,'boundary_interval_pts':[last['pts'],t] if last is not None else None,'frames':[],'hero_preflop_candidate_files':[],'label_episodes':[],'complete_hand_verified':False,'positions_verified':False};segments.append(current);hero=board=None;folded=False
            if h is not None:hero=set(h)
            if b is not None:board=b
            if h is not None and b==[]:current['hero_preflop_candidate_files'].append(r['file'])
            reading=r.get('action_reading');label=(reading.get('candidate') or {}).get('action') if reading else None
            current['frames'].append({'file':r['file'],'pts':t,'street_candidate':{0:'empty',3:'flop',4:'turn',5:'river'}.get(len(b)) if b is not None else None,'after_fold_label':folded,'fold_label':label=='fold'})
            folded=folded or label=='fold';last=r
    index={r['file']:r for r in rows}
    for s in segments:
        labeled=[{'table_id':s['table_id'],'seat':1,'pts':f['pts'],'file':f['file'],'reading':index[f['file']]['action_reading']} for f in s['frames'] if index[f['file']].get('action_reading') is not None]
        s['label_episodes']=[{**{k:v for k,v in e.items() if k!='seat'},'role':'hero_roi_candidate'} for e in episodes(labeled,max_gap=max_gap)[0]]
    need(sum(len(s['frames']) for s in segments)+len(unassigned)==len(rows),'Incomplete timeline coverage')
    return {'segments':segments,'unassigned':unassigned,'hands_reconstructed':False,'actions_verified':False,'automatic_clip_selection_authorized':False}


def run(jobs,windows,output,*,cache_capacity=512):
    from plo5_recognition_cache import ExactReader
    bank,snapshots=calibration(jobs);out=Path(output);need(out.parent.is_dir() and not out.exists() and not out.is_symlink(),'New output directory required')
    need(type(windows) is list and 1<=len(windows)<=8,'Invalid windows');total=0;used=set()
    with tempfile.TemporaryDirectory(prefix='.plo5-dense-',dir=out.parent) as tmp:
        stage=Path(tmp);reports=[];readers={}
        for i,w in enumerate(windows):
            need(type(w) is dict and set(w)=={'job_id','start','seconds'} and w['job_id'] in snapshots,'Invalid window')
            j,b,ah,early,m=snapshots[w['job_id']];reader=readers.get(w['job_id'])
            if reader is None:
                reader=ExactReader(cache_capacity);readers[w['job_id']]=reader
            start,seconds=w['start'],w['seconds'];need(type(start) is int and type(seconds) is int and 2<=seconds<=60 and start>early and start+seconds+1<m['media']['duration_seconds'],'Window overlaps training or exceeds source')
            keys={(w['job_id'],x) for x in range(start,start+seconds)};need(not keys&used,'Overlapping windows');used|=keys;total+=seconds*len(m['regions']);need(total<=512,'Dense crop budget exceeded')
            folder=stage/f'window_{i+1:02d}';folder.mkdir();source=Path(OfflineJobStore(j['database']).get(j['job_id'])['source_path']);size=(m['media']['width'],m['media']['height']);fs=extract(source,start,seconds,folder,size);rows=[]
            for n,f in enumerate(fs):
                with Image.open(folder/f['file']) as im:
                    for r in m['regions']:
                        x,y,width,height=(r[k] for k in ('x','y','width','height'));crop=im.crop((x,y,x+width,y+height)).convert('RGB');name=f"table_{r['table_id']:02d}_{n+1:03d}.png";crop.save(folder/name);p=observe(crop,bank);action=None
                        if p['visible'] is True:
                            action=reader.read(crop,'action')
                        rows.append({'file':name,'sha256':sha256(folder/name),'source_frame':f['file'],'source_frame_sha256':f['sha256'],'table_id':r['table_id'],'pts':f['pts'],**p,'action_reading':action})
            result=timeline(rows);report={'variant':5,'job_id':w['job_id'],'source_sha256':b['source_sha256'],'sparse_manifest_sha256':b['reports']['evidence/ingest/manifest.json'],'annotation_sha256':ah,'start':start,'seconds':seconds,'frames':fs,'observations':rows,**result,'pixel_comparison_independent':False,'video_verified':False,'equity_ev_authorized':False};write(folder/'timeline.json',report)
            reports.append({'window':folder.name,'start':start,'seconds':seconds,'frames':len(fs),'observations':len(rows),'segments':len(result['segments']),'unassigned':len(result['unassigned']),'full_hero_candidates':sum(r['hero_cards'] is not None for r in rows),'board_candidates':sum(r['board_cards'] is not None for r in rows),'label_episodes':sum(len(s['label_episodes']) for s in result['segments']),'post_fold_frames':sum(f['after_fold_label'] for s in result['segments'] for f in s['frames'])});print(json.dumps(reports[-1]),flush=True)
        for j,b,ah,_,_ in snapshots.values():need(read_bound_evidence(j['database'],j['job_id'])==b and load(j['annotations'])[1]==ah,'Source changed')
        summary={'variant':5,'status':'DENSE_CANDIDATE_TIMELINES','windows':reports,'ocr_cache_by_job':{k:v.stats() for k,v in readers.items()},'hands_reconstructed':False,'actions_verified':False,'automatic_clip_selection_authorized':False,'independent_human_reference_verified':False};write(stage/'summary.json',summary);need(not out.exists() and not out.is_symlink(),'Output appeared');os.rename(stage,out)
    return summary


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('jobs');p.add_argument('windows');p.add_argument('output');p.add_argument('--cache-capacity',type=int,default=512);a=p.parse_args(argv);run(load(a.jobs)[0],load(a.windows)[0],a.output,cache_capacity=a.cache_capacity);return 0


if __name__=='__main__':raise SystemExit(main())
