"""Offline PLO5 video beta: selective study report, never certifies its inputs."""
import argparse
import hashlib
import html
import json
import os
import re
import tempfile
from pathlib import Path
from PIL import Image
from plo5_pre_gto_context import need
from plo5_selective_review import select, STREETS, VERSION, identity, hash_ok
from plo5_error_prints import capture, read
from plo5_mixed_money import STARTS

CSS = 'body{font:16px system-ui,sans-serif;background:#f4f6f8;color:#172334;max-width:900px;margin:auto;padding:20px}article,section{background:white;border:1px solid #dce1e8;border-radius:12px;padding:16px;margin:12px 0}h1,h2,h3{margin:.5em 0}small,figcaption{color:#526174}figure{margin:12px 0}img{max-width:100%;height:auto;border-radius:8px}summary{cursor:pointer;font-weight:600}table{border-collapse:collapse;width:100%}td,th{text-align:left;padding:6px;border-bottom:1px solid #ddd}code{overflow-wrap:anywhere}.warning{background:#fff5db;border:1px solid #ddbb64;padding:12px;border-radius:8px}.metrics{display:flex;gap:20px;flex-wrap:wrap}.loss{font-weight:bold;color:#9c2828}'


def esc(v):return html.escape(str(v),quote=True)


def num(v):return format(v,'.12g').replace('.',',')


def span(b):return num(b[0]) if b[0]==b[1] else num(b[0])+' a '+num(b[1])


def action(k):
    a,n=k.split(':');label={'fold':'Fold','check':'Check','call':'Call','bet':'Bet','raise':'Raise'}[a]
    return label+(' ('+n+' unidades de ficha)' if int(n) else '')


def records_from(obj):
    need(type(obj) is dict,'Decision object required')
    if obj.get('version')==VERSION and set(obj)=={'version','decisions'}:return obj['decisions']
    need(obj.get('hands_reconstructed') is False and type(obj.get('decision_records')) is list,'Unsupported decision input')
    return obj['decision_records']


def assets(selection,manifest_path,dest):
    """Validate exact selection and copy unique PNGs; hashes are integrity only."""
    m=read(manifest_path);root=Path(manifest_path).parent
    need(m.get('version')=='plo5-error-prints-v1' and m.get('streets')==selection['streets'] and hash_ok(m.get('source_sha256')),'Print manifest scope mismatch')
    need(m.get('errors')==selection['errors'] and m.get('unresolved')==selection['unresolved'] and m.get('adequate_count')==selection['adequate_count'],'Print manifest selection mismatch')
    expected={identity(e):e for e in selection['print_requests']};errors={identity(e):e for e in selection['errors']};rows=m.get('decision_prints')
    need(type(rows) is list and len(rows)==len(expected)<=512,'Print roster mismatch')
    found={};copies={};total=0
    for r in rows:
        k=identity(r);need(k in expected and k not in found,'Unexpected print decision')
        e=expected[k];need(all(r.get(a)==v for a,v in e.items() if a!='status') and r.get('source_sha256')==m['source_sha256'] and r.get('status')=='EXACT_FRAME_CROP' and r.get('error')==errors[k],'Print binding mismatch')
        name=r.get('file');need(type(name) is str and re.fullmatch(r'frame_[0-9]{5}_table_[1-4]\.png',name) is not None and name.endswith('_table_'+str(e['table_id'])+'.png'),'Unsafe print filename')
        t=e['table_id'];x=STARTS[t-1];right=STARTS[t] if t<4 else 1504;box=[x,0,right,696]
        need(r.get('crop')==box and hash_ok(r.get('png_sha256')),'Invalid crop identity')
        ref=(e['source_sha256'],e['pts'],e['rgb_sha256'],t,r['png_sha256'])
        if name in copies:need(copies[name]==ref,'Conflicting shared crop')
        else:
            p=root/name;need(p.is_file() and not p.is_symlink() and 0<p.stat().st_size<=4*1024**2,'Missing or oversized print');raw=p.read_bytes()
            need(hashlib.sha256(raw).hexdigest()==r['png_sha256'],'PNG hash mismatch')
            from io import BytesIO
            with Image.open(BytesIO(raw)) as im:
                need(im.format=='PNG' and im.size==(right-x,696),'PNG geometry mismatch');im.verify()
            total+=len(raw);need(total<=512*1024**2,'Asset budget exceeded')
            (dest/name).write_bytes(raw);copies[name]=ref
        found[k]=r
    return found,len(copies),total


def render(records,selection,prints,demo):
    by_id={identity(d):d for d in records};groups={}
    for e in selection['errors']:groups.setdefault(e['hand_id'],[]).append(e)
    yield '<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>PLO Trainee — Revisão PLO5</title><style>'+CSS+'</style><main><h1>PLO Trainee — Revisão PLO5</h1>'
    if demo:yield '<p class="warning"><strong>DEMONSTRAÇÃO FICTÍCIA.</strong> Os valores estratégicos são simulados; nenhuma imagem comprova um erro real.</p>'
    yield '<p class="warning">Comparações de EV dependem dos intervalos e certificados declarados na entrada. Não há certificação GTO independente nem validação semântica automática dos prints.</p>'
    yield '<p>Streets: '+esc(', '.join(selection['streets']))+'</p><div class="metrics"><span>Erros selecionados: <strong>'+str(len(selection['errors']))+'</strong></span><span>Decisões adequadas: '+str(selection['adequate_count'])+'</span><span>Pendentes: '+str(len(selection['unresolved']))+'</span></div>'
    if not groups:yield '<p>Nenhum erro demonstrado pelos dados disponíveis. Isso não significa que todas as decisões foram corretas.</p>'
    for hand,errors in groups.items():
        yield '<section><h2>Mão '+esc(hand)+'</h2>'
        for e in sorted(errors,key=lambda a:(STREETS.index(a['street']),a['decision_id'])):
            k=identity(e);d=by_id[k];ev=d['action_ev_bounds'];a,b=e['actual'],e['recommended'];r=prints.get(k);odds=e['pot_odds']
            yield '<article><h3>'+esc(e['street'].upper())+' · Decisão '+esc(e['decision_id'])+' · '+esc(e['severity'])+'</h3><p><strong>Você fez:</strong> '+esc(action(a))+'<br><strong>Alternativa recomendada (EV superior):</strong> '+esc(action(b))+'</p>'
            yield '<p>EV da ação: '+span(ev[a])+' BB | EV da alternativa: '+span(ev[b])+' BB<br>Pot odds brutas: '+('Não aplicável/indisponível' if odds is None else num(100*odds)+'%')+'</p><p class="loss">Perda de EV demonstrada: '+span([e['ev_loss_lower_bb'],e['ev_loss_upper_bb']])+' BB</p>'
            if r:yield '<figure><img loading="lazy" decoding="async" alt="Recorte da mesa" src="prints/'+esc(r['file'])+'"><figcaption>Mesa '+str(r['table_id'])+' · PTS '+esc(r['pts'])+' s · '+('antes' if r['phase']=='before' else 'depois')+' · integridade verificada; vínculo semântico não certificado.</figcaption></figure>'
            else:yield '<p><small>Print pendente — erro preservado mesmo sem imagem.</small></p>'
            yield '<details><summary>Ver fundamentação matemática</summary><p>EV incremental em BB. Limite inferior da diferença: limite inferior da alternativa menos limite superior da ação. A alternativa supera a ação no modelo declarado; não é necessariamente a única ótima.</p><table><tr><th>Ação</th><th>Intervalo de EV (BB)</th></tr>'
            for name,value in sorted(ev.items()):yield '<tr><td>'+esc(action(name))+'</td><td>'+span(value)+'</td></tr>'
            yield '</table><p>Pot odds são o preço imediato bruto, sem garantia de realização de equity. Gravidade usa limite inferior de EV: marginal abaixo de 1 BB, relevante de 1 a menos de 5, grave a partir de 5. Nenhum limite exclui erro positivo.</p><small>Certificado declarado: <code>'+esc(d['certificate_sha256'])+'</code></small></details></article>'
        yield '</section>'
    if selection['unresolved']:
        yield '<details><summary>Diagnóstico separado ('+str(len(selection['unresolved']))+' pendências)</summary><p>Não são erros nem acertos demonstrados.</p><ul>'
        for d in selection['unresolved']:yield '<li>'+esc(d['hand_id'])+' / '+esc(d['decision_id'])+' / '+esc(d['street'])+' — '+esc(d['reason'])+'</li>'
        yield '</ul></details>'
    yield '<footer><small>Revisão offline de sessão encerrada. Resultado financeiro não utilizado. DriveHUD fora do beta.</small></footer></main></html>'


def build(records,output,streets=STREETS,*,prints=None,demo=False):
    out=Path(output);need(not out.exists() and not out.is_symlink() and out.parent.is_dir(),'New report directory required');need(type(demo) is bool,'Invalid demo flag')
    selection=select(records,streets)
    with tempfile.TemporaryDirectory(prefix='.plo21-',dir=out.parent) as tmp:
        stage=Path(tmp)/'report';stage.mkdir();dest=stage/'prints';dest.mkdir()
        rows,n,size=assets(selection,prints,dest) if prints is not None else ({},0,0)
        with (stage/'index.html').open('w',encoding='utf-8') as f:
            for chunk in render(records,selection,rows,demo):f.write(chunk)
        result=dict(version='plo5-study-report-v1',streets=selection['streets'],errors=len(selection['errors']),adequate=selection['adequate_count'],unresolved=len(selection['unresolved']),decision_prints=len(rows),unique_crops=n,png_bytes=size,html_bytes=(stage/'index.html').stat().st_size,demo=demo,certificates_independently_verified=False,semantic_binding_verified=False,drivehud_beta=False)
        (stage/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        need(not out.exists() and not out.is_symlink(),'Output appeared');os.rename(stage,out)
    return result


def video_report(source,recognition,records,output,streets=STREETS,*,demo=False):
    with tempfile.TemporaryDirectory() as t:
        p=Path(t)/'captures';capture(source,recognition,records,p,streets)
        return build(records,output,streets,prints=p/'manifest.json',demo=demo)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('decisions');p.add_argument('output');p.add_argument('--streets',nargs='+',choices=STREETS,default=list(STREETS));p.add_argument('--prints');p.add_argument('--video');p.add_argument('--recognition');p.add_argument('--demo',action='store_true');a=p.parse_args(argv)
    need(bool(a.video)==bool(a.recognition) and not (a.video and a.prints),'Provide video+recognition or an existing print manifest');records=records_from(read(a.decisions))
    r=video_report(a.video,read(a.recognition),records,a.output,a.streets,demo=a.demo) if a.video else build(records,a.output,a.streets,prints=a.prints,demo=a.demo)
    print(json.dumps(r,ensure_ascii=False));return 0

if __name__=='__main__':raise SystemExit(main())
