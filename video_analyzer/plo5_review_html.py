"""Self-contained offline Portuguese HTML reports; no scripts or remote assets."""
from html import escape
from pathlib import Path
from hashlib import sha256
from base64 import b64encode
from plo5_pre_gto_context import need


def text(v):return escape(str(v),quote=True)


def action_name(v):return {'fold':'Desistir','check':'Passar','call':'Pagar','bet':'Apostar','raise':'Aumentar'}.get(v,v)


def num(v):return 'Não disponível' if v is None else f'{v:.3f}'.replace('.',',')


def screenshot(root,frame):
    name=frame['file'];need(type(name) is str and Path(name).name==name and name.lower().endswith('.png'),'Invalid screenshot name')
    p=Path(root)/name;need(p.is_file() and not p.is_symlink() and p.stat().st_size<=4*1024**2,'Invalid screenshot')
    raw=p.read_bytes();need(raw.startswith(b'\x89PNG\r\n\x1a\n') and sha256(raw).hexdigest()==frame['sha256'],'Screenshot mismatch')
    return '<figure><img alt="Frame da gravação" src="data:image/png;base64,'+b64encode(raw).decode('ascii')+'"><figcaption>Tempo de origem: '+text(frame['pts'])+' s — '+text(name)+'</figcaption></figure>'


def render(result,*,root=None,frames=()):
    need(len(frames)<=20,'Screenshot budget exceeded')
    chunks=['<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>PLO Trainee — Revisão</title><style>body{font:16px system-ui,sans-serif;background:#f5f6f8;color:#182235;max-width:980px;margin:auto;padding:24px}h1{font-size:26px}section,details{background:white;border:1px solid #dce1e8;border-radius:12px;padding:18px;margin:14px 0}summary{cursor:pointer;font-weight:600}table{border-collapse:collapse;width:100%}td,th{text-align:left;padding:8px;border-bottom:1px solid #e0e4eb}img{max-width:100%;height:auto}figure{margin:12px 0}small,figcaption{color:#536174}.metric{font-size:24px;font-weight:700}code{overflow-wrap:anywhere}</style><h1>PLO Trainee — Revisão pós-sessão</h1>']
    status=result['status'];chunks.append('<section><h2>Resultado</h2><p>'+text(status)+'</p>')
    if result['evidence']=='DECLARED_INPUT' and 'action' in result:
        chunks.append('<p>Posição: '+text(result['position'])+' | Mão: '+text(' '.join(result['holding']))+' | Board: '+text(' '.join(result['board']))+'</p><p>Decisão: '+text(action_name(result['action'][0]))+' ('+text(result['action'][1])+' fichas)'+'</p><p class="metric">EV estimado: '+num(result['ev_bb'])+' BB</p><p>Pot odds: '+('Não aplicável' if result['pot_odds_gross'] is None else num(100*result['pot_odds_gross'])+'%')+'</p><p>'+text(result['verdict'])+'</p><p>Diferença para a melhor ação modelada: '+num(result['ev_gap_bb'])+' BB</p><small>Modelo restrito, ranges declarados; não é certificação GTO. '+text(result['pot_odds_scope'])+'</small></section>')
        chunks.append('<details><summary>Ver detalhes técnicos</summary><p>'+text(result.get('ev_scope','Ação não comparável no modelo.'))+'</p><p>NashConv global: '+num(result['nashconv_bb'])+' BB. Não limita isoladamente o erro local.</p><p>Backend: '+text(result['backend'])+'; iterações: '+text(result['iterations'])+'; distribuições: '+text(result['legal_deals'])+'</p><table><tr><th>Ação</th><th>Fichas</th><th>Frequência</th><th>EV (BB)</th></tr>')
        for a in result['actions']:chunks.append('<tr><td>'+text(action_name(a['action']))+'</td><td>'+text(a['amount'])+'</td><td>'+num(a['frequency']*100)+'%</td><td>'+num(a['ev_bb'])+'</td></tr>')
        chunks.append('</table><p>Cache: <code>'+text(result['cache_key'])+'</code></p>')
        if 'rank' in result:chunks.append('<p>Índice e rank matemático (não equity): '+text(result['rank'])+'</p>')
        if 'bridge_key' in result:chunks.append('<p>Origem pré-flop: '+text(result['bridge_key'])+'; procedência do treinamento não verificada; TV dos pesos: '+text(result['joint_weight_tv'])+'</p>')
        chunks.append('</details>')
    elif result['evidence']=='UNVERIFIED_VIDEO':
        chunks.append('<p>Sem EV: histórico, cartas e posições ainda não verificados. Mudanças do valor exibido não comprovam ganhos, perdas ou rebuys.</p><p>Slots examinados: '+text(result['samples'])+' | Mudanças: '+text(len(result['changes']))+'</p></section><details><summary>Ver mudanças observadas</summary><table><tr><th>Mesa</th><th>Tempo (s)</th><th>Delta stack (BB)</th><th>Delta pote (BB)</th></tr>')
        for c in result['changes']:chunks.append('<tr><td>'+text(c['table_id'])+'</td><td>'+text(c['after_pts'])+'</td><td>'+text(c.get('stack_delta_bb','—'))+'</td><td>'+text(c.get('pot_delta_bb','—'))+'</td></tr>')
        chunks.append('</table><p>SHA-256 do vídeo: <code>'+text(result.get('source_sha256'))+'</code></p></details>')
    elif 'net_bb' in result:
        chunks.append('<p>Liquidação declarada; não certificada por vídeo. Resultado líquido (BB): '+text(result['net_bb'])+'; divergências: '+text(result['errors'])+'</p></section>')
    else:
        chunks.append('<p>Histórico pré-flop declarado. Sem EV certificado.</p></section><details><summary>Ver sequência</summary><p>'+text(result['history'])+'</p></details>')
    if frames:
        chunks.append('<details><summary>Ver prints da gravação</summary>')
        for f in frames:chunks.append(screenshot(root,f))
        chunks.append('</details>')
    return ''.join(chunks)+'<p><small>Uso offline, após a sessão. Resultados dependem do modelo e da evidência disponível.</small></p></html>'


def write(path,result,**kwargs):
    p=Path(path);need(p.suffix=='.html' and not p.exists() and not p.is_symlink(),'New HTML required')
    html=render(result,**kwargs);need(len(html.encode('utf-8'))<=128*1024**2,'Report size budget exceeded')
    with p.open('x',encoding='utf-8') as f:f.write(html)
