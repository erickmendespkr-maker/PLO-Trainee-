"""Offline PLO5 review package: one independent media audit per dense window."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import hashlib
import html
import io
import json
import os
from pathlib import Path
import re
import tempfile
import time
from PIL import Image
from plo5_window_review import build, need


def sha(data):return hashlib.sha256(data).hexdigest()
def esc(value):return html.escape(str(value),quote=True)
def dump(path,obj):
    with Path(path).open('x',encoding='utf-8') as f:json.dump(obj,f,ensure_ascii=False,indent=2,allow_nan=False)


def render(stage,review,roster):
    """Copy every audited crop; show candidate data, not linked strategic decisions."""
    stage=Path(stage);(stage/'prints').mkdir(); owners={}
    for s in review['segments']:
        for r in s['frames']:
            need(r['file'] not in owners,'Duplicate segment crop');owners[r['file']]=(s['candidate_id'],r)
    for r in review['unassigned']:
        need(r['file'] not in owners,'Duplicate unassigned crop');owners[r['file']]=(None,r)
    need(set(owners)==set(roster) and len(roster)==review['observations'],'Incomplete review roster')
    rows=[];articles=[];total=0
    for n,(name,(path,obs)) in enumerate(sorted(roster.items(),key=lambda kv:(kv[1][1]['table_id'],kv[1][1]['pts'])),1):
        owner,r=owners[name];need(path.is_file() and not path.is_symlink() and 0<path.stat().st_size<=32*1024**2,'Unsafe crop')
        data=path.read_bytes();need(sha(data)==obs['sha256'],'Crop changed');total+=len(data);need(total<=2*1024**3,'Media budget exceeded')
        dest=f'prints/{n:05d}.png';(stage/dest).write_bytes(data)
        tid=obs['table_id'];pts=obs['pts'];info=' | '.join(f'{k}: {r.get(v) if r.get(v) is not None else "não reconhecido"}' for k,v in [('Hero','hero'),('Board','board'),('Ação','label'),('Stack BB','stack_bb'),('Pote BB','pot_bb')]) if owner else r['reason']
        articles.append(f'<article data-table="{tid}"><h2>Mesa {tid} — {esc(pts)} s</h2><p>{esc(owner or "Não atribuído")}</p><img loading="lazy" src="{dest}" alt="Print da mesa {tid}"><p>{esc(info)}</p></article>')
        rows.append({'source_crop':name,'file':dest,'sha256':obs['sha256'],'table_id':tid,'pts':pts,'candidate_id':owner})
    page='''<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src 'self' file:; style-src 'unsafe-inline'; script-src 'unsafe-inline'"><title>PLO5 — Revisão visual</title><style>body{font:16px system-ui;margin:24px;color:#17212b;background:#f5f5f5}article{background:white;padding:16px;margin:16px 0;max-width:900px}img{max-width:100%;height:auto}[hidden]{display:none}</style><h1>PLO5 — Revisão visual</h1><p>Leituras candidatas; mão, posição, resultado financeiro e erro estratégico não confirmados. A variação do stack não comprova perda. Não é GTO.</p>'''
    if (stage/'study'/'index.html').is_file():page+='<p><a href="study/index.html">Relatório estratégico revisado (amostras separadas; sem associação automática)</a></p>'
    page+='<label>Mesa <select id="table"><option value="">Todas</option>'+''.join(f'<option>{t}</option>' for t in sorted({r['table_id'] for r in rows}))+'</select></label>'+''.join(articles)+'''<script>document.getElementById('table').onchange=function(){for(const a of document.querySelectorAll('article'))a.hidden=!!(this.value&&a.dataset.table!==this.value);};</script></html>'''
    (stage/'index.html').write_text(page,encoding='utf-8')
    return {'prints':rows,'media_bytes':total,'mp4_rendered':0}


def run(job,inputs,output,*,extract=False,workers=2,capacity=512,mode='quick',study=None):
    from plo5_financial_observations import bound_window, amount
    from plo5_recognition_cache import ExactReader
    from plo5_ingest_job import read_bound_evidence
    from offline_video_ingest_probe import sha256
    need(type(workers) is int and 1<=workers<=3 and mode in ('quick','deep'),'Invalid settings')
    need(type(inputs) is list and 1<=len(inputs)<=8,'Invalid windows')
    need(type(job) is dict and set(job)=={'database','job_id','annotations'},'Invalid job')
    out=Path(output);need(out.parent.is_dir() and not out.exists() and not out.is_symlink(),'New output directory required')
    reader=ExactReader(capacity);times={};items=[];roster={};refs=[];binding=None;started=time.perf_counter()
    def timed(key,fn):
        start=time.perf_counter();result=fn();times[key]=times.get(key,0)+time.perf_counter()-start;return result
    with tempfile.TemporaryDirectory(prefix='.plo5-review-',dir=out.parent) as tmp:
        stage=Path(tmp)/'package';stage.mkdir()
        if extract:
            from plo5_dense_timeline import run as dense
            need(all(type(w) is dict and w.get('job_id')==job['job_id'] for w in inputs),'Wrong extraction job')
            timed('extract_and_recognize',lambda:dense([job],inputs,stage/'dense',cache_capacity=capacity))
            paths=sorted((stage/'dense').glob('window_*/timeline.json'));need(len(paths)==len(inputs),'Missing extracted windows')
        else:paths=[Path(p) for p in inputs]
        for p in paths:
            t,th,b,crops=timed('independent_media_audit',lambda:bound_window(job,p))
            need(binding is None or binding==b,'Job binding changed');binding=b;refs.append((p,th))
            for f in t['frames']:refs.append((p.parent/f['file'],f['sha256']))
            def scan(o):
                cp=crops[o['file']];data=cp.read_bytes();need(sha(data)==o['sha256'],'Crop changed during read')
                with Image.open(io.BytesIO(data)) as im:
                    im=im.convert('RGB');pot=reader.read(im,'pot') if o['visible'] is True else None;stack=reader.read(im,'stack') if o['visible'] is True else None
                return {'file':o['file'],'table_id':o['table_id'],'pts':o['pts'],'crop_sha256':o['sha256'],'pot_bb':amount(pot),'stack_bb':amount(stack),'pot_reading':pot,'stack_reading':stack}
            def scan_all():
                with ThreadPoolExecutor(max_workers=workers) as pool:return list(pool.map(scan,t['observations']))
            rows=timed('money_ocr',scan_all)
            m={'variant':5,'job_id':t['job_id'],'source_sha256':t['source_sha256'],'timeline_sha256':th,'financial_result_verified':False,'observations':rows}
            name=p.parent.name;items.append({'window':name,'timeline':t,'money':m})
            for o in t['observations']:
                key=name+'/'+o['file'];need(key not in roster,'Duplicate crop identity');roster[key]=(crops[o['file']],o);refs.append((crops[o['file']],o['sha256']))
        review=timed('fusion',lambda:build(items));dump(stage/'review.json',review);dump(stage/'money.json',[x['money'] for x in items])
        if study is not None:
            from plo5_visual_report import run as visual
            need(type(study) is dict and set(study)=={'drafts','study_input'},'Invalid study inputs')
            for p in study.values():refs.append((Path(p),sha256(p)))
            timed('separate_strategy_report',lambda:visual(job['database'],job['job_id'],study['drafts'],study['study_input'],stage/'study',mode))
        media=timed('visual_report',lambda:render(stage,review,roster))
        def recheck():
            need(read_bound_evidence(job['database'],job['job_id'])==binding and sha256(job['annotations'])==review['annotation_sha256'] and all(sha256(p)==h for p,h in refs),'Inputs changed')
        timed('final_recheck',recheck)
        report={'variant':5,'status':'OFFLINE_REVIEW_PACKAGE','job_id':review['job_id'],'source_sha256':review['source_sha256'],'windows':len(items),'observations':review['observations'],'candidate_segments':len(review['segments']),'unassigned':len(review['unassigned']),'money_cache':reader.stats(),'stage_seconds':times,'wall_seconds':time.perf_counter()-started,'study_present':study is not None,'dense_strategy_link_verified':False,'financial_result_verified':False,'hands_reconstructed':False,'gto_solution':False,'ev_loss_bb':None,**media}
        dump(stage/'manifest.json',report);need(not out.exists() and not out.is_symlink(),'Output appeared');os.rename(stage,out)
    return report


def main(argv=None):
    from plo5_session_export import load
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('job');p.add_argument('windows');p.add_argument('output');p.add_argument('--extract',action='store_true');p.add_argument('--workers',type=int,default=2);p.add_argument('--capacity',type=int,default=512);p.add_argument('--mode',choices=('quick','deep'),default='quick');p.add_argument('--study');a=p.parse_args(argv)
    r=run(load(a.job)[0],load(a.windows)[0],a.output,extract=a.extract,workers=a.workers,capacity=a.capacity,mode=a.mode,study=load(a.study)[0] if a.study else None);print(json.dumps({k:v for k,v in r.items() if k!='prints'},ensure_ascii=False));return 0


if __name__=='__main__':raise SystemExit(main())
