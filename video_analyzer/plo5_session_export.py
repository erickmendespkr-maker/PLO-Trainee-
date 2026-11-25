"""Offline PLO5 session package: declared hand intervals, reports and audited MP4 crops."""
import argparse
from collections import defaultdict
from bisect import bisect_left
import json
import os
from pathlib import Path
import subprocess
import tempfile

from plo5_ingest_job import read_bound_evidence
from offline_jobs import OfflineJobStore
from offline_ingest_pts_audit import read_manifest, decoded_pts, unique_pairs
from offline_video_ingest_probe import sha256, regions_from_json
from plo5_leak_review import aggregate, identity, need, number, digest, identifier
from plo5_individual_report import build, quoted


def load(path):
    p=Path(path);need(p.is_file() and not p.is_symlink() and 0<p.stat().st_size<=32*1024*1024,'Unsafe JSON')
    raw=p.read_bytes();need(len(raw)<=32*1024*1024,'Oversized JSON')
    import hashlib
    return json.loads(raw,object_pairs_hook=unique_pairs),hashlib.sha256(raw).hexdigest()


def write(path,obj):
    with path.open('x',encoding='utf-8') as f:json.dump(obj,f,ensure_ascii=False,indent=2,allow_nan=False)


def plan(binding, manifest, drafts, draft_sha, request, pts):
    need(type(request) is dict and set(request)=={'bundle','clip_reviews'},'Invalid export request')
    b=request['bundle'];summary=aggregate(b)
    expected={**binding,'manifest_sha256':binding['reports']['evidence/ingest/manifest.json'],'draft_sha256':draft_sha}
    identity(b,expected)
    need(drafts.get('variant')==5 and all(drafts.get(k)==expected[k] for k in ('job_id','source_sha256','manifest_sha256')) and drafts.get('status')=='unverified_hand_timeline_drafts' and all(drafts.get(k) is False for k in ('hands_reconstructed','actions_verified','equity_ev_authorized','automatic_clip_selection_authorized')),'Invalid draft identity')
    need(manifest['source_sha256']==expected['source_sha256'],'Manifest source mismatch')
    samples={s['file']:s for s in manifest['samples']};seen={};segments={};regions={r['table_id']:r for r in manifest['regions']}
    need(len(samples)==len(manifest['samples']),'Duplicate sample')
    def bind(f,tid,did):
        name=f['file'];s=samples.get(name)
        need(name not in seen and s is not None and tid in regions and s['table_id']==tid and s['sha256']==f['crop_sha256'] and s['actual_frame_timestamp_seconds']==f['pts'],'Evidence frame mismatch')
        seen[name]=did
    for d in drafts['drafts']:
        did=d['draft_id'];fs=d['frames'];tid=d['table_id']
        need(identifier(did) and did not in segments and d['hand_id'] is None and d['complete_hand_verified'] is False and fs and [f['pts'] for f in fs]==sorted(set(f['pts'] for f in fs)),'Invalid draft segment')
        for f in fs:bind(f,tid,did)
        segments[did]=(tid,fs)
    for f in drafts['unassigned']:bind(f,f['table_id'],None)
    need(set(seen)==set(samples) and set(segments)==set(b['draft_ids']),'Incomplete draft coverage')
    for e in b['expected_decisions']:need(seen.get(e['action_file'])==e['draft_id'],'Unbound expected action')
    for r in b['reports']:
        for kind in ('context','action'):
            name=r[kind+'_file'];need(seen.get(name)==r['draft_id'] and samples[name]['actual_frame_timestamp_seconds']==r[kind+'_pts'],'Unbound decision evidence')
    reviews=request['clip_reviews'];need(type(reviews) is list and len(reviews)<=32,'Clip count exceeds budget')
    need(pts and all(a<b for a,b in zip(pts,pts[1:])),'Ambiguous decoded source PTS')
    jobs={};total=0
    for r in reviews:
        need(type(r) is dict and set(r)=={'draft_id','start_pts','end_pts','reviewer','complete_by_review'} and r['complete_by_review'] is True and identifier(r['reviewer']),'Explicit full-hand interval review required')
        did=r['draft_id'];need(did in segments and did not in jobs,'Unknown/duplicate clip review')
        tid,fs=segments[did];start,end=number(r['start_pts']),number(r['end_pts'])
        i,j=bisect_left(pts,start),bisect_left(pts,end)
        need(i<len(pts) and j<len(pts) and pts[i]==start and pts[j]==end and i<j and 0<end-start<=300,'Bounds must be distinct decoded PTS within clip budget')
        need(start<=fs[0]['pts']<=fs[-1]['pts']<=end,'Clip omits segment evidence')
        need(all(seen[name]==did for name,s in samples.items() if s['table_id']==tid and start<=s['actual_frame_timestamp_seconds']<=end),'Clip crosses unrelated or unassigned evidence')
        need(all(x['table_id']!=tid or end<x['start_pts'] or start>x['end_pts'] for x in jobs.values()),'Overlapping same-table clips')
        total+=end-start;need(total<=1800,'Total clip duration budget exceeded')
        jobs[did]={**r,'table_id':tid,'region':regions[tid],'start_frame':i,'end_frame_inclusive':j}
    return summary,jobs


def command(args,timeout=180):
    p=subprocess.run(args,stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=timeout,check=False)
    need(p.returncode==0,'Media command failed: '+p.stderr[-500:]);return p.stdout


def frame_hashes(path,filters=None,*,max_frames=None):
    args=['ffmpeg','-v','error','-threads','1','-filter_threads','1','-i',str(path),'-map','0:v:0']
    if filters:args+=['-vf',filters]
    else:args+=['-vf','format=yuv420p']
    if max_frames is not None:
        need(type(max_frames) is int and max_frames>0,'Invalid source frame limit')
        args+=['-frames:v',str(max_frames)]
    out=command(args+['-an','-fps_mode','passthrough','-f','framemd5','-'])
    return [line.split(',')[-1].strip() for line in out.splitlines() if line and not line.startswith('#')]


def render(source,out,p,pts,*,preset="ultrafast"):
    need(preset in ("ultrafast","superfast"),"Unsupported lossless encoding preset")
    r=p['region'];i,j=p['start_frame'],p['end_frame_inclusive']
    vf=f"trim=start_frame={i}:end_frame={j+1},crop={r['width']}:{r['height']}:{r['x']}:{r['y']},setpts=PTS-STARTPTS,format=yuv420p"
    # MP4 must retain a positive duration on the final encoded packet.
    last_delta=pts[j+1]-pts[j] if j+1<len(pts) else pts[j]-pts[j-1]
    packet_duration=max(1,round(last_delta*1000000))
    command(['ffmpeg','-v','error','-nostdin','-n','-threads','1','-filter_threads','1','-i',str(source),'-map','0:v:0','-vf',vf,'-an','-c:v','libx264','-threads','1','-preset',preset,'-crf','0','-pix_fmt','yuv420p','-fps_mode','passthrough','-enc_time_base','1:1000000','-bsf:v',f'setts=duration={packet_duration}','-frames:v',str(j-i+1),str(out)])
    meta=json.loads(command(['ffprobe','-v','error','-show_entries','stream=codec_type,codec_name,width,height:format=duration','-of','json',str(out)]))
    streams=meta['streams'];need(len(streams)==1 and streams[0]['codec_type']=='video' and streams[0]['codec_name']=='h264' and (streams[0]['width'],streams[0]['height'])==(r['width'],r['height']),'Clip media mismatch')
    actual=decoded_pts(out);expected=[t-pts[i] for t in pts[i:j+1]]
    need(len(actual)==len(expected) and all(abs(a-b)<=0.000002 for a,b in zip(actual,expected)),'Clip frame/PTS mismatch')
    src_hashes=frame_hashes(source,vf,max_frames=j-i+1);out_hashes=frame_hashes(out)
    need(len(src_hashes)==len(expected) and src_hashes==out_hashes,'Clip decoded pixel mismatch')
    return {'file':out.name,'sha256':sha256(out),'frames':len(actual),'width':r['width'],'height':r['height'],'duration_seconds':float(meta['format']['duration']),'relative_pts_audited':True,'decoded_yuv420p_pixels_match':True,'audio_included':False,'encoding_preset':preset,'complete_hand_verified':False}


def run(database,job_id,draft_path,request_path,new_dir,*,preset="ultrafast"):
    need(preset in ("ultrafast","superfast"),"Unsupported lossless encoding preset")
    binding=read_bound_evidence(database,job_id);job=OfflineJobStore(database).get(job_id)
    root=Path(job['result_path']).parent;source=Path(job['source_path']);manifest=read_manifest(root/'evidence/ingest/manifest.json')
    need(regions_from_json(root/'regions.json',manifest['media']['width'],manifest['media']['height'])==manifest['regions'],'Region mismatch')
    drafts,dh=load(draft_path);request,rh=load(request_path);pts=decoded_pts(source)
    summary,plans=plan(binding,manifest,drafts,dh,request,pts);bundle=request['bundle']
    out=Path(new_dir);need(out.parent.is_dir() and not out.parent.is_symlink() and not out.exists() and not out.is_symlink(),'New output directory required')
    by_draft=defaultdict(list)
    with tempfile.TemporaryDirectory(prefix='.plo5-session-',dir=out.parent) as tmp:
        stage=Path(tmp);items=[]
        for i,r in enumerate(sorted(bundle['reports'],key=lambda r:r['action_file']),1):
            single={**bundle,'reports':[r],'expected_decisions':[{'draft_id':r['draft_id'],'action_file':r['action_file']}]}
            report=build(single);name=f'decision_{i:05d}';write(stage/(name+'.json'),report)
            (stage/(name+'.txt')).write_text(report['text'],'utf-8')
            item={'draft_id':r['draft_id'],'action_file':r['action_file'],'decision_report_sha256':report['sources']['decision_report_sha256'],'json':name+'.json','text':name+'.txt','clip':None}
            items.append(item);by_draft[r['draft_id']].append(item)
        clips=[]
        for i,(did,p) in enumerate(sorted(plans.items()),1):
            meta=render(source,stage/f'hand_{i:04d}.mp4',p,pts,preset=preset)
            clips.append({**p,**meta,'decision_files':[x['json'] for x in by_draft[did]]})
            for x in by_draft[did]:x['clip']=meta['file']
        summary['exported_decisions']=items;summary['clips']=clips
        summary['unreviewed_clip_draft_ids']=sorted(set(bundle['draft_ids'])-set(plans))
        summary['clip_selection']='explicit_manual_review_only';summary['complete_hands_verified']=False
        write(stage/'session.json',summary)
        o=summary['overall'];f=summary['financial'];lines=['PLO TRAINEE — SESSÃO PLO5 (CONDICIONAL)',f"Decisões declaradas: {o['declared_decisions']}; relatórios: {o['reports_received']}; comparáveis: {o['fully_comparable_decisions']}.",f"Padrões inferiores condicionais: {o['conditional_inferior_decisions']}; não são leaks verificados.",f"Resultado financeiro condicional: {f['conditional_net_bb']} BB; segmentos reconciliados: {f['reconciled_drafts']}/{f['drafts_declared']}.",f'Cortes MP4 revisados por declaração: {len(clips)}. Completude das mãos não verificada.','EV loss real, GTO e variância: indisponíveis.','Relatórios e vínculos: session.json.']
        for x in items:lines.append(quoted(x['action_file'])+' — '+x['text']+' — '+(x['clip'] or 'sem corte'))
        (stage/'session.txt').write_text('\n'.join(lines)+'\n','utf-8')
        manifest_out={'variant':5,'status':'CONDITIONAL_SESSION_PACKAGE','job_id':job_id,'source_sha256':binding['source_sha256'],'manifest_sha256':binding['reports']['evidence/ingest/manifest.json'],'draft_sha256':dh,'request_sha256':rh,'files':{p.name:sha256(p) for p in sorted(stage.iterdir())},'video_verified':False,'complete_hands_verified':False,'automatic_clip_selection_authorized':False}
        write(stage/'package_manifest.json',manifest_out)
        need(sha256(draft_path)==dh and sha256(request_path)==rh and read_bound_evidence(database,job_id)==binding,'Inputs changed during export')
        need(not out.exists() and not out.is_symlink(),'Output appeared during export');os.rename(stage,out)
    return manifest_out


def verify(directory):
    p=Path(directory);need(p.is_dir() and not p.is_symlink(),'Invalid package directory')
    m,_=load(p/'package_manifest.json');need(m.get('variant')==5 and m.get('status')=='CONDITIONAL_SESSION_PACKAGE' and all(m.get(k) is False for k in ('video_verified','complete_hands_verified','automatic_clip_selection_authorized')),'Invalid package manifest')
    need(set(m['files'])=={x.name for x in p.iterdir()}-{'package_manifest.json'},'Package inventory mismatch')
    for name,h in m['files'].items():
        f=p/name;need(Path(name).name==name and f.is_file() and not f.is_symlink() and sha256(f)==h,'Package file hash mismatch')
    return m


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('database');p.add_argument('job_id');p.add_argument('drafts');p.add_argument('request');p.add_argument('output');p.add_argument('--preset',choices=('ultrafast','superfast'),default='ultrafast');a=p.parse_args(argv)
    run(a.database,a.job_id,a.drafts,a.request,a.output,preset=a.preset);return 0


if __name__=='__main__':raise SystemExit(main())
