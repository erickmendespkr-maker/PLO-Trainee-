"""Reproducible synthetic four-table offline PLO5 load exercise (Linux)."""
import argparse
from collections import Counter
import json
from pathlib import Path
import resource
import subprocess
import time

from PIL import Image, ImageDraw, ImageFont
from local_ingest import ingest_local
from plo5_ingest_job import run_job, read_bound_evidence
from offline_ingest_pts_audit import read_manifest, decoded_pts
from offline_video_ingest_probe import probe, sample_times, sha256
from plo5_hand_drafts import analyze_job
from plo5_ground_truth import template, evaluate
from plo5_session_export import run as export, verify, write
from plo5_leak_review import need

FELT=(20,100,40)
HERO=['As','Kd','Qh','Jc','Ts']
BOARD=['2c','3d','4h','5s','6c']
STAGES=(0,3,4,5,0,3,5)


def command(args):
    subprocess.run(args,stdin=subprocess.DEVNULL,check=True,capture_output=True,timeout=180)


def usage():
    own=resource.getrusage(resource.RUSAGE_SELF);child=resource.getrusage(resource.RUSAGE_CHILDREN)
    return {'cpu_seconds':own.ru_utime+own.ru_stime+child.ru_utime+child.ru_stime,
            'python_peak_rss_kib':own.ru_maxrss,'largest_terminated_child_peak_rss_kib':child.ru_maxrss}


def size(root):
    return sum(p.stat().st_size for p in root.rglob('*') if p.is_file() and not p.is_symlink())


def fixture(root,duration):
    need(type(duration) is int and 3<=duration<=3600,'Duration must be 3–3600 seconds')
    root=Path(root);templates=root/'templates';templates.mkdir()
    font=ImageFont.truetype('DejaVuSans.ttf',26);small=ImageFont.truetype('DejaVuSans.ttf',20)
    for kind,labels in [('rank','23456789TJQKA'),('suit','cdhs')]:
        for label in labels:
            symbol=dict(c='♣',d='♦',h='♥',s='♠')[label] if kind=='suit' else label
            im=Image.new('RGB',(32,32),'white');d=ImageDraw.Draw(im);l,t,r,b=d.textbbox((0,0),symbol,font=font)
            d.text(((32-r+l)//2-l,(32-b+t)//2-t),symbol,font=font,fill='black');im.save(templates/f'{kind}_{label}.png')
    regions=[{'table_id':i+1,'x':(i%2)*320,'y':(i//2)*320,'width':320,'height':320} for i in range(4)]
    cards={'variant':5,'rank_roi':[2,2,32,32],'suit_roi':[2,34,32,32],'tables':[]}
    context={'variant':5,'tables':[]};actions={'variant':5,'tables':[]}
    for r in regions:
        tid=r['table_id'];cards['tables'].append({'table_id':tid,'board':[[i*48,0,44,70] for i in range(5)],'hero':[[i*48,80,44,70] for i in range(5)]})
        t={'table_id':tid,'hero_seat':1,'pot':[0,224,104,30],'blinds':[106,224,104,30],'seats':[]}
        for j in range(2):t['seats'].append({'seat':j+1,'stack':[0,256+j*32,104,30],'bet':[106,256+j*32,104,30],'dealer':[212+j*32,224,30,30]})
        context['tables'].append(t);actions['tables'].append({**t,'seats':[dict(s,action=[212,256+j*32,104,30]) for j,s in enumerate(t['seats'])]})
    for name,value in [('regions',{'tables':regions}),('cards',cards),('context',context),('actions',actions),('calibration',{'felt_rgb':list(FELT),'tolerance':30,'board_strip':{'offset_x':0,'offset_y':0,'step_x':48,'width':44,'height':10,'white_min_rgb':200,'min_white_fraction':.6}})]:write(root/(name+'.json'),value)
    for phase,n in enumerate(STAGES):
        full=Image.new('RGB',(640,640),FELT)
        for region,cp,ctx in zip(regions,cards['tables'],context['tables']):
            im=Image.new('RGB',(320,320),FELT);d=ImageDraw.Draw(im)
            for key,tokens in [('hero',HERO),('board',BOARD[:n])]:
                for (x,y,w,h),token in zip(cp[key],tokens):
                    im.paste('white',(x,y,x+w,y+h))
                    for kind,label,dy in [('rank',token[0],2),('suit',token[1],34)]:
                        with Image.open(templates/f'{kind}_{label}.png') as g:im.paste(g,(x+2,y+dy))
            for rect,text in [(ctx['pot'],f"{10+region['table_id']+phase} BB"),(ctx['blinds'],'0.5/1 BB'),(ctx['seats'][0]['stack'],'90 BB'),(ctx['seats'][1]['stack'],'80 BB'),(ctx['seats'][0]['bet'],'2 BB'),(ctx['seats'][1]['bet'],'1 BB'),(ctx['seats'][0]['dealer'],'D')]:
                x,y,w,h=rect;d.rectangle((x,y,x+w-1,y+h-1),fill='white');d.text((x+3,y+2),text,font=small,fill='black')
            full.paste(im,(region['x'],region['y']))
        full.save(root/f'phase{phase}.png')
    cycle=root/'cycle.mp4';video=root/'synthetic.mp4'
    command(['ffmpeg','-v','error','-framerate','1','-i',str(root/'phase%d.png'),'-frames:v','7','-c:v','libx264','-threads','1','-g','7','-bf','0','-crf','12','-pix_fmt','yuv420p',str(cycle)])
    command(['ffmpeg','-v','error','-stream_loop','-1','-i',str(cycle),'-t',str(duration),'-c','copy',str(video)])
    return video


def run(root,*,duration=3600,interval=120):
    root=Path(root);need(root.parent.is_dir() and not root.exists() and not root.is_symlink(),'New output directory required');root.mkdir(mode=0o700)
    stages={}
    def step(name,fn):
        start=time.perf_counter();before=usage();result=fn();after=usage()
        stages[name]={'wall_seconds':time.perf_counter()-start,'cpu_seconds':after['cpu_seconds']-before['cpu_seconds'],'python_peak_rss_kib':after['python_peak_rss_kib'],'largest_terminated_child_peak_rss_kib':after['largest_terminated_child_peak_rss_kib'],'retained_bytes':size(root)}
        print(name,json.dumps(stages[name]),flush=True);return result
    start=time.perf_counter();video=step('fixture',lambda:fixture(root,duration));media=probe(video);pts=decoded_pts(video)
    need(media['duration_seconds']==duration and pts==list(range(duration)),'Synthetic media PTS/duration mismatch')
    db=root/'jobs.db';job=step('queue',lambda:ingest_local(video,root/'uploads',db));jid=job['job_id']
    result=step('ingest_audit',lambda:run_job(db,jid,root/'regions.json',root/'evidence',interval=interval,pixel_checks=16))
    binding=read_bound_evidence(db,jid);manifest=read_manifest(Path(result['result_path']).parent/'evidence/ingest/manifest.json')
    times=sample_times(duration,media['frame_rate_reported'],interval);expected={(i,t) for i in range(1,5) for t in times}
    samples=manifest['samples'];need(len(samples)==len(expected) and {(s['table_id'],s['actual_frame_timestamp_seconds']) for s in samples}==expected,'Sample coverage mismatch')
    d=step('recognition',lambda:analyze_job(db,jid,root/'cards.json',root/'templates',root/'context.json',root/'actions.json',root/'calibration.json',max_tasks=4096,max_gap=30))
    dp=root/'drafts.json';write(dp,d);dh=sha256(dp)
    ann=template(binding,manifest);ann.update(dataset_kind='synthetic_fixture',reviewer='fixture_generator',independent_review=True)
    for row in ann['annotations']:
        phase=int(row['pts'])%7;row['truth']={'visible':True,'hero_cards':HERO,'board':BOARD[:STAGES[phase]],'pot_bb':str(10+row['table_id']+phase),'hero_stack_bb':'90','position':'BTN/SB','hero_action_label':None}
    validation=step('annotation_comparison',lambda:evaluate(binding,manifest,d,dh,ann));write(root/'annotation_metrics.json',validation)
    # No real hand boundaries or action histories; only declared synthetic media intervals.
    drafts=d['drafts'];need(drafts,'No draft segments for synthetic fixture')
    clips=[]
    for tid in range(1,5):
        for seg in (s for s in drafts if s['table_id']==tid):
            first=seg['frames'][0]['pts'];last=seg['frames'][-1]['pts'];end=min(duration-1,max(last,first+1))
            if first<end and not any(first<=s['actual_frame_timestamp_seconds']<=end and s['table_id']==tid and s['file'] not in {f['file'] for f in seg['frames']} for s in samples):
                clips.append({'draft_id':seg['draft_id'],'start_pts':first,'end_pts':end,'reviewer':'synthetic_interval_fixture','complete_by_review':True});break
    need(len(clips)==4,'Expected one synthetic clip per table')
    b={**{k:d[k] for k in ('variant','job_id','source_sha256','manifest_sha256')},'draft_sha256':dh,'draft_ids':[s['draft_id'] for s in drafts],'expected_decisions':[],'reports':[],'financial_report':None}
    rp=root/'request.json';write(rp,{'bundle':b,'clip_reviews':clips})
    pack=step('export',lambda:export(db,jid,dp,rp,root/'package'));need(step('verify',lambda:verify(root/'package'))==pack,'Package verification mismatch')
    session=json.loads((root/'package/session.json').read_text());need(read_bound_evidence(db,jid)==binding,'Evidence changed')
    need(len(session['clips'])==4 and all(c['relative_pts_audited'] and c['decoded_yuv420p_pixels_match'] for c in session['clips']),'Clip audit incomplete')
    report={'variant':5,'status':'SYNTHETIC_LOAD_PASS','dataset_kind':'synthetic_fixture','media':media,'decoded_source_frames':len(pts),'tables':4,'interval_seconds':interval,'samples_expected':len(expected),'samples_audited':len(samples),'pixel_spotchecks':binding['crops_pixel_checked'],'sampled_frames_per_table':dict(Counter(s['table_id'] for s in samples)),'draft_segments':len(drafts),'unassigned_samples':len(d['unassigned']),'draft_frame_count':sum(len(s['frames']) for s in drafts),'clips':session['clips'],'decision_reports':0,'source_bytes':video.stat().st_size,'source_sha256':sha256(video),'package_bytes':size(root/'package'),'retained_bytes_before_report':size(root),'stages':stages,'total_wall_seconds':time.perf_counter()-start,'real_session_validated':False,'complete_hands_verified':False,'full_session_decisions_verified':False,'gto_solution':False,'automatic_clip_selection_authorized':False}
    need(report['draft_frame_count']+report['unassigned_samples']==len(samples),'Draft coverage mismatch');write(root/'load_report.json',report);return report


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('output');p.add_argument('--duration',type=int,default=3600);p.add_argument('--interval',type=int,default=120);a=p.parse_args(argv)
    run(a.output,duration=a.duration,interval=a.interval);return 0


if __name__=='__main__':raise SystemExit(main())
