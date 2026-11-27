"""Offline session reports: bound table crops and batched declared model reviews."""
import argparse
import base64
import hashlib
import io
import json
from pathlib import Path
from PIL import Image
from plo5_pre_gto_context import need
from plo5_mixed_money import STARTS
from plo5_review import visual, postflop
from plo5_review_html import text, num, action_name

MAX_REPORT = 64*1024**2


def digest(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def read_json(path):
    p=Path(path);need(p.is_file() and not p.is_symlink() and 0<p.stat().st_size<=MAX_REPORT,'Invalid JSON input')
    raw=p.read_bytes();obj=json.loads(raw);need(type(obj) is dict,'JSON object required')
    return obj,hashlib.sha256(raw).hexdigest()


def page(body):
    result='<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>PLO Trainee — Revisão da sessão</title><style>body{font:16px system-ui;background:#f5f6f8;color:#182235;max-width:980px;margin:auto;padding:20px}article{background:white;border:1px solid #dce1e8;border-radius:12px;padding:16px;margin:12px 0}summary{cursor:pointer;font-weight:600}figure{margin:8px 0}img{max-width:100%;height:auto}figcaption,small{color:#536174}.pair{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}td,th{padding:6px;text-align:left;border-bottom:1px solid #ddd}table{border-collapse:collapse;width:100%}code{overflow-wrap:anywhere}</style><h1>PLO Trainee — Revisão pós-sessão</h1>'+''.join(body)+'</html>'
    need(len(result.encode('utf-8'))<=MAX_REPORT,'Report size budget exceeded');return result


def table_crop(root,frame,table):
    need(type(table) is int and 1<=table<=4,'Invalid table')
    name=frame['file'];need(type(name) is str and Path(name).name==name and name.lower().endswith('.png'),'Invalid frame name')
    p=Path(root)/name;need(p.is_file() and not p.is_symlink() and 0<p.stat().st_size<=4*1024**2,'Invalid frame file')
    raw=p.read_bytes();need(hashlib.sha256(raw).hexdigest()==frame['sha256'],'Frame hash mismatch')
    with Image.open(io.BytesIO(raw)) as im:
        need(im.format=='PNG' and im.size==(1504,696),'Unsupported frame geometry')
        x=STARTS[table-1];right=STARTS[table] if table<4 else 1504
        patch=im.convert('RGB').crop((x,0,right,696));buf=io.BytesIO();patch.save(buf,format='PNG')
    return base64.b64encode(buf.getvalue()).decode('ascii')


def visual_session(manifest_path,source=None,*,max_changes=100):
    need(type(max_changes) is int and 1<=max_changes<=200,'Invalid change budget')
    m,mhash=read_json(manifest_path);r=visual(m);root=Path(manifest_path).parent
    source_checked=False
    if source is not None:
        p=Path(source);need(p.is_file() and not p.is_symlink() and p.suffix.lower()=='.mp4','Invalid source video')
        need(digest(p)==m['source_sha256'],'Source video hash mismatch');source_checked=True
    need(len(r['changes'])<=max_changes,'Change budget exceeded; split the session')
    frames={f['file']:f for f in m['frames']};crops={};body=['<p>Ocorrências visuais para revisão. Não são mãos, perdas, rebuys ou ações confirmadas. EV e pot odds não calculados sem contexto completo.</p>',f'<p>Slots examinados: {r["samples"]} | Ocorrências: {len(r["changes"])}</p>']
    for i,c in enumerate(r['changes'],1):
        t=c['table_id'];body.append(f'<article><h2>{i}. Mesa {t} — {text(c["platform"])}</h2><p>Stack: {text(c.get("stack_delta_bb","—"))} BB | Pote: {text(c.get("pot_delta_bb","—"))} BB</p><p>Sem decisão estratégica confirmada.</p><details><summary>Ver prints e evidência</summary><div class="pair">')
        for key,label in (('before_file','Antes'),('after_file','Depois')):
            f=frames[c[key]];k=(f['file'],t)
            if k not in crops:crops[k]=table_crop(root,f,t)
            body.append(f'<figure><img loading="lazy" alt="{label}, mesa {t}" src="data:image/png;base64,{crops[k]}"><figcaption>{label}: {text(f["pts"])} s — {text(f["file"])}</figcaption></figure>')
        body.append('</div><p><small>Recortes de slots fixos; hash do PNG conferido, leitura ainda não certificada.</small></p></details></article>')
    body.append('<small>Manifesto SHA-256: <code>'+mhash+'</code>. Vídeo: '+('hash conferido' if source_checked else 'hash não rechecado')+'. Não houve nova auditoria de extração de frames neste relatório.</small>')
    return page(body),dict(status='VISUAL_EVIDENCE_ONLY',changes=len(r['changes']),unique_crops=len(crops),source_hash_checked=source_checked,manifest_sha256=mhash,ev_authorized=False)


def review_batch(cache,models,*,cfr_executable=None,rank_executables=None,rank_reader=None,rank_worker=None):
    need(rank_worker is None or rank_executables is None and rank_reader is None,'Conflicting rank backends')
    need(type(models) is list and 1<=len(models)<=64,'Invalid model batch')
    required={'id','context','history','holding','action','rake_on_fold'};optional={'iterations','pot_bps','joint'}
    seen=set();rows=[]
    for m in models:
        need(type(m) is dict and required<=set(m)<=required|optional,'Invalid model fields')
        ident=m['id'];need(type(ident) is str and 0<len(ident)<=100 and ident not in seen,'Duplicate or invalid decision ID');seen.add(ident)
        r=postflop(cache,**{k:v for k,v in m.items() if k!='id'},cfr_executable=cfr_executable)
        rows.append(dict(id=ident,result=r))
    if rank_worker is not None:
        for street in (3,4,5):
            selected=[x['result'] for x in rows if len(x['result']['board'])==street]
            if selected:
                ranks=rank_worker.lookup(street,[(r['holding'],r['board']) for r in selected])
                for r,v in zip(selected,ranks):r['rank']=v
    if rank_executables is not None:
        from plo5_rank_service import lookup_states
        need(type(rank_executables) in (tuple,list) and len(rank_executables)==2,'Invalid rank executables')
        for street in (3,4,5):
            selected=[x['result'] for x in rows if len(x['result']['board'])==street]
            if selected:
                ranks=lookup_states(rank_executables[0],rank_reader,street,[(r['holding'],r['board']) for r in selected],rank_executable=rank_executables[1])
                for r,v in zip(selected,ranks):r['rank']=v
    return rows


def model_page(rows):
    body=['<p>Decisões com dados declarados e modelo restrito. Não constituem mãos confirmadas por vídeo nem estratégia GTO certificada.</p>']
    for row in rows:
        r=row['result'];v=r['ev_bb'];sign='EV positivo' if v is not None and v>1e-8 else 'EV negativo' if v is not None and v< -1e-8 else 'EV aproximadamente zero' if v is not None else 'EV indisponível'
        odds='Não aplicável' if r['pot_odds_gross'] is None else num(100*r['pot_odds_gross'])+'%'
        body.append('<article><h2>'+text(row['id'])+'</h2><p>'+text(r['position'])+' | '+text(' '.join(r['holding']))+' | Board: '+text(' '.join(r['board']))+'</p><p><strong>'+text(action_name(r['action'][0]))+' — '+sign+': '+num(v)+' BB</strong></p><p>Pot odds brutas para pagar: '+odds+' | Diferença para maior EV modelado: '+num(r['ev_gap_bb'])+' BB</p><details><summary>Ver detalhes técnicos</summary><p>'+text(r['status'])+'; '+text(r['verdict'])+'. '+text(r.get('ev_scope',''))+' '+text(r['pot_odds_scope'])+'</p><p>NashConv global: '+num(r['nashconv_bb'])+' BB; não limita erro local. Backend: '+text(r['backend'])+'; iterações: '+text(r['iterations'])+'.</p><table><tr><th>Ação</th><th>Fichas</th><th>Frequência</th><th>EV (BB)</th></tr>')
        for a in r['actions']:body.append('<tr><td>'+text(action_name(a['action']))+'</td><td>'+text(a['amount'])+'</td><td>'+num(a['frequency']*100)+'%</td><td>'+num(a['ev_bb'])+'</td></tr>')
        body.append('</table><p>Cache: <code>'+text(r['cache_key'])+'</code></p>')
        if 'rank' in r:body.append('<p>Rank matemático, não equity: '+text(r['rank'])+'</p>')
        body.append('</details></article>')
    return page(body)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('visual','models'));p.add_argument('input');p.add_argument('output');p.add_argument('--video');p.add_argument('--cache');p.add_argument('--native');p.add_argument('--index');p.add_argument('--rank');p.add_argument('--persistent-rank');a=p.parse_args(argv)
    out=Path(a.output);need(out.suffix=='.html' and not out.exists() and not out.is_symlink(),'New HTML required')
    if a.mode=='visual':html,stats=visual_session(a.input,a.video)
    else:
        need(a.cache is not None and bool(a.index)==bool(a.rank),'Cache and paired rank executables required')
        d,_=read_json(a.input);need(set(d)=={'decisions'},'Invalid batch fields')
        need(not a.persistent_rank or not a.index,'Conflicting rank backends')
        if a.persistent_rank:
            from plo5_rank_worker import RankWorker
            with RankWorker(a.persistent_rank) as worker:
                rows=review_batch(a.cache,d['decisions'],cfr_executable=a.native,rank_worker=worker)
        else:
            rows=review_batch(a.cache,d['decisions'],cfr_executable=a.native,rank_executables=(a.index,a.rank) if a.index else None)
        html=model_page(rows);stats=dict(status='DECLARED_MODELS_ONLY',decisions=len(rows),cache_hits=sum(x['result']['cache_hit'] for x in rows),gto_solution=False)
    with out.open('x',encoding='utf-8') as f:f.write(html)
    print(json.dumps(stats,ensure_ascii=False));return 0

if __name__=='__main__':raise SystemExit(main())
