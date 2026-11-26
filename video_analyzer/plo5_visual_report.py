"""Offline PLO5 HTML report using existing audited crops; no video rendering."""
import argparse
import hashlib
import html
import json
import os
from pathlib import Path
import re
import tempfile
import time


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def esc(value):
    return html.escape(str(value), quote=True)


def render(folder, samples, drafts, study, crop_root, output, *, recheck):
    """Render the already validated roster, copying each crop exactly once."""
    out = Path(output)
    require(out.parent.is_dir() and not out.exists() and not out.is_symlink(), 'New output directory required')
    require(len(samples) <= 10000 and len(samples) > 0, 'Invalid crop count')
    indexed = {s['file']: s for s in samples}
    require(len(indexed) == len(samples), 'Duplicate crop')
    owners = {}
    for d in drafts['drafts']:
        for f in d['frames']:
            require(f['file'] not in owners, 'Duplicate segment crop')
            owners[f['file']] = d['draft_id']
    for f in drafts['unassigned']:
        require(f['file'] not in owners, 'Duplicate unassigned crop')
        owners[f['file']] = None
    require(set(owners) == set(indexed), 'Incomplete crop coverage')
    decisions = {d['action_file']: d for d in study['decisions']}
    require(len(decisions) == len(study['decisions']) and all(f in owners and owners[f] is not None and owners[f] == d['draft_id'] for f,d in decisions.items()), 'Unbound decision')
    begin = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix='.plo5-visual-', dir=out.parent) as tmp:
        stage = Path(tmp) / 'report'; stage.mkdir(); (stage/'prints').mkdir()
        sections = []; records = []; total = 0
        for n,s in enumerate(sorted(samples,key=lambda x:(x['table_id'],x['actual_frame_timestamp_seconds'],x['file'])),1):
            name = s['file']; require(re.fullmatch(r'[A-Za-z0-9_-]+\.(?:png|jpg|jpeg)',name) is not None,'Unsafe crop name')
            src = Path(crop_root)/name
            require(src.is_file() and not src.is_symlink() and 0 < src.stat().st_size <= 32*1024*1024,'Invalid crop')
            data = src.read_bytes(); require(sha(data)==s['sha256'],'Crop hash mismatch')
            total += len(data); require(total <= 2*1024**3,'Report media budget exceeded')
            target = f'prints/{n:05d}{src.suffix.lower()}'; (stage/target).write_bytes(data)
            tid = s['table_id']; pts = s['actual_frame_timestamp_seconds']; owner = owners[name]; d = decisions.get(name)
            classification = d['classification'] if d else 'SEM_DECISAO_VINCULADA'
            explanation = d['text'] if d else 'Evidência visual sem decisão estratégica vinculada. Não permite concluir erro, ganho ou perda.'
            sections.append(f'<article id="print-{n:05d}" data-table="{esc(tid)}" data-class="{esc(classification)}"><h2>Mesa {esc(tid)} · {esc(pts)} s</h2><p>Segmento: {esc(owner or "não atribuído")} | {esc(classification)}</p><img loading="lazy" src="{target}" alt="Print da mesa {esc(tid)}"><pre>{esc(explanation)}</pre></article>')
            records.append({'source_crop':name,'file':target,'sha256':s['sha256'],'table_id':tid,'pts':pts,'draft_id':owner,'classification':classification})
        options = ''.join(f'<option value="{esc(t)}">Mesa {esc(t)}</option>' for t in sorted({s['table_id'] for s in samples}))
        classes = ''.join(f'<option>{esc(c)}</option>' for c in sorted({r['classification'] for r in records}))
        head = '''<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src 'self' file:; style-src 'unsafe-inline'; script-src 'unsafe-inline'"><title>PLO5 — Relatório de estudo</title><style>body{font:16px system-ui;margin:24px;background:#f5f5f5;color:#17212b}article{background:white;border:1px solid #ddd;padding:16px;margin:16px 0;max-width:900px}img{max-width:100%;height:auto}pre{white-space:pre-wrap;font:inherit}label{margin-right:16px} [hidden]{display:none}</style><h1>PLO5 — Relatório de estudo</h1><p>Segmentos e modelos condicionais, não mãos completas nem erros verificados. Resultado financeiro e EV são distintos. Não é solução GTO.</p>'''
        filters = f'<p><label>Mesa <select id="table"><option value="">Todas</option>{options}</select></label><label>Classificação <select id="classification"><option value="">Todas</option>{classes}</select></label></p>'
        script = '''<script>const t=document.getElementById('table'),c=document.getElementById('classification');function filter(){for(const a of document.querySelectorAll('article'))a.hidden=!!((t.value&&a.dataset.table!==t.value)||(c.value&&a.dataset.class!==c.value));}t.onchange=c.onchange=filter;</script></html>'''
        (stage/'index.html').write_text(head+filters+''.join(sections)+script,encoding='utf-8')
        report = {'variant':5,'status':'VISUAL_CONDITIONAL_STUDY_ONLY','job_id':folder['job_id'],'source_sha256':folder['source_sha256'],'study_input_digest':study['input_digest'],'prints':records,'decisions_linked':len(decisions),'media_bytes':total,'mp4_rendered':0,'video_verified':False,'strategic_error_established':False,'gto_solution':False,'ev_loss_bb':None}
        (stage/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
        recheck()
        require(not out.exists() and not out.is_symlink(),'Output appeared')
        os.rename(stage,out)
    return {**report,'render_wall_seconds':time.perf_counter()-begin}


def run(database,job_id,draft_path,study_path,output,mode='quick'):
    from plo5_ingest_job import read_bound_evidence
    from offline_jobs import OfflineJobStore
    from offline_ingest_pts_audit import read_manifest
    from plo5_session_export import load, plan
    from plo5_study_report import build
    binding = read_bound_evidence(database,job_id)
    root = Path(OfflineJobStore(database).get(job_id)['result_path']).parent/'evidence/ingest'
    manifest = read_manifest(root/'manifest.json')
    drafts,dh = load(draft_path); payload,ph = load(study_path)
    # No clips requested: the existing plan validates identities and roster using audited sample PTS.
    pts = sorted({s['actual_frame_timestamp_seconds'] for s in manifest['samples']})
    plan(binding,manifest,drafts,dh,{'bundle':payload['bundle'],'clip_reviews':[]},pts)
    study = build(payload,mode)
    def recheck():
        require(read_bound_evidence(database,job_id)==binding and load(draft_path)[1]==dh and load(study_path)[1]==ph,'Inputs changed')
    return render(binding,manifest['samples'],drafts,study,root,output,recheck=recheck)


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('database');p.add_argument('job_id');p.add_argument('drafts');p.add_argument('study_input');p.add_argument('output');p.add_argument('--mode',choices=('quick','deep'),default='quick');a=p.parse_args()
    r=run(a.database,a.job_id,a.drafts,a.study_input,a.output,a.mode);print(json.dumps({k:v for k,v in r.items() if k!='prints'},ensure_ascii=False))
