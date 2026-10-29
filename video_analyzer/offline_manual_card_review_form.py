"""Generate a local human card/frame review form; no OCR claims or network requests.

Usage: python offline_manual_card_review_form.py BINDING_JSON clip.mp4 NEW_HTML
"""
import argparse
import json
from pathlib import Path
from offline_plo_equity_monte_carlo import read_json, require
from offline_reviewed_equity_clip_report import check_binding, digest, safe_file

HTML = '''<!doctype html><html lang="pt-BR"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PLO Trainee — revisão manual offline</title>
<style>body{font:16px system-ui;background:#f5f7fa;color:#172333;margin:20px}
main{max-width:860px;margin:auto;background:white;padding:22px;border-radius:12px}
video{width:100%;max-height:420px;background:#101820}fieldset{margin:14px 0;padding:14px}
.row{display:flex;gap:8px;margin:8px 0;align-items:center;flex-wrap:wrap}
.row input{width:65px}input,textarea,select,button{font:inherit;padding:5px}
textarea{width:98%}.warning{background:#fff3dc;padding:12px}</style>
<main><h1 id="identity"></h1>
<p class="warning">Revisão humana: nenhuma carta ou ação é confirmada automaticamente.
O registro do quadro é uma declaração do revisor, não uma prova de reconhecimento visual.
A ação OCR não é atribuída ao herói nem classificada como correta/incorreta.</p>
<video id="video" controls preload="metadata" src="clip.mp4"></video>
<p>Pause o vídeo e clique em <b>Registrar quadro</b> para cada carta visível.</p>
<form id="form" novalidate>
<fieldset><legend>Cartas privadas revisadas</legend><div id="hero"></div></fieldset>
<fieldset><legend>Board revisado</legend><label>Quantidade de cartas
<select id="board-count"><option>3</option><option>4</option><option selected>5</option></select></label>
<div id="board"></div></fieldset>
<fieldset><legend>Hipóteses matemáticas</legend>
<label>Range adversário <select id="range-kind"><option value="uniform">Uniforme</option>
<option value="weighted_combos">Combinações ponderadas</option></select></label>
<p><label>Combinações ponderadas (JSON) <textarea id="combos" rows="3" disabled></textarea></label></p>
<label>Simulações <input id="iterations" type="number" value="1000" min="2" max="50000"></label>
<label>Semente <input id="seed" type="number" value="42" min="0" max="4294967295"></label>
<label>Pote antes do call <input id="pot" type="number" min="0" placeholder="opcional"></label>
<label>Custo do call <input id="call" type="number" min="0" placeholder="opcional"></label>
</fieldset>
<fieldset><legend>Confirmação manual</legend>
<label>Notas sobre legibilidade e incertezas<textarea id="notes" rows="3" required></textarea></label>
<p><label><input id="confirm" type="checkbox"> Examinei manualmente os quadros e confirmei as cartas digitadas.</label></p>
</fieldset>
<p id="message" role="status"></p><button id="export" type="submit">Exportar revisão JSON local</button>
</form><small>Sem recursos externos. SHA-256 do MP4: <code id="clip-sha"></code></small>
</main><script type="application/json" id="context">__CONTEXT__</script><script>
'use strict';const $=id=>document.getElementById(id),ctx=JSON.parse($('context').textContent);
$('identity').textContent='Revisão '+ctx.variant+' / Mesa '+ctx.table_id+' / Mão '+ctx.hand_id;
$('clip-sha').textContent=ctx.source_clip_sha256;
function row(kind,i){let d=document.createElement('div');d.className='card-row row';
let l=document.createElement('label');l.textContent=(kind==='hero'?'Privada ':'Board ')+(i+1);
let c=document.createElement('input');c.className='card';c.maxLength=2;c.placeholder='As';
let b=document.createElement('button');b.type='button';b.className='capture';b.textContent='Registrar quadro';
let t=document.createElement('output');t.className='time';t.dataset.seconds='';t.textContent='Não registrado';
b.onclick=()=>{let v=$('video');if(v.readyState<1){$('message').textContent='Carregue o vídeo.';return;}
t.dataset.seconds=String(v.currentTime);t.textContent=v.currentTime.toFixed(3)+' s';};
d.append(l,c,b,t);return d;}
const hole=ctx.variant==='PLO5'?5:6;
for(let i=0;i<hole;i++)$('hero').append(row('hero',i));
function board(){let p=$('board');p.replaceChildren();for(let i=0;i<Number($('board-count').value);i++)p.append(row('board',i));}
$('board-count').onchange=board;board();
$('range-kind').onchange=()=>$('combos').disabled=$('range-kind').value!=='weighted_combos';
function integer(id,min,max){let s=$(id).value.trim(),v=Number(s);if(!/^\\d+$/.test(s)||!Number.isSafeInteger(v)||v<min||v>max)throw Error('Número inválido: '+id);return v;}
function amount(id){let s=$(id).value.trim();if(!s)return null;let v=Number(s);if(!Number.isFinite(v)||v<0||v>1e9)throw Error('Valor inválido: '+id);return v;}
function review(){let video=$('video');if(video.readyState<1)throw Error('Vídeo não carregado.');
let seen=new Set(),e=[];
for(let r of document.querySelectorAll('.card-row')){let c=r.querySelector('.card').value.trim();
if(!/^[23456789TJQKA][cdhs]$/.test(c))throw Error('Carta inválida: '+c);
if(seen.has(c))throw Error('Carta repetida: '+c);seen.add(c);
let stamp=r.querySelector('.time').dataset.seconds;
if(stamp==='')throw Error('Registre quadro para '+c);
let t=Number(stamp);if(!Number.isFinite(t)||t<0||t>video.duration+0.01)throw Error('Quadro fora do clipe.');
e.push({card:c,clip_timestamp_seconds:t});}
let notes=$('notes').value.trim();if(notes.length<8||notes.length>2000)throw Error('Notas devem ter 8 a 2000 caracteres.');
if(!$('confirm').checked)throw Error('Confirmação manual obrigatória.');
let iterations=integer('iterations',2,50000),seed=integer('seed',0,4294967295);
let pot=amount('pot'),call=amount('call');if((pot===null)!==(call===null))throw Error('Informe pote e call juntos.');
let model={kind:'uniform'};
if($('range-kind').value==='weighted_combos'){
let combos;try{combos=JSON.parse($('combos').value);}catch{throw Error('JSON de range inválido.');}
if(!Array.isArray(combos)||combos.length<1||combos.length>1000)throw Error('Range ponderado inválido.');
model={kind:'weighted_combos',combos};}
let out={schema_version:1,source_binding_sha256:ctx.source_binding_sha256,source_clip_sha256:ctx.source_clip_sha256,
hand_id:ctx.hand_id,table_id:ctx.table_id,proposal_index:ctx.proposal_index,variant:ctx.variant,
manual_cards_confirmed:true,review_method:'manual_video_frame_review',review_notes:notes,
hero_cards:e.slice(0,hole).map(x=>x.card),board_cards:e.slice(hole).map(x=>x.card),
card_frame_evidence:e,opponent_model:model,iterations,seed};
if(pot!==null){out.pot_now=pot;out.call_cost=call;}return out;}
$('form').onsubmit=ev=>{ev.preventDefault();try{let obj=review();let blob=new Blob([JSON.stringify(obj,null,2)+'\\n'],{type:'application/json'});
let url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='manual_review_'+ctx.hand_id+'.json';
document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
$('message').textContent='JSON exportado. Revise os dados antes da análise.';}
catch(err){$('message').textContent=err.message;}};
</script></html>'''


def render(binding, binding_sha, clip_sha):
    check_binding(binding)
    require(binding['clip_sha256'] == clip_sha, 'clip hash differs from evidence binding')
    context = {k: binding[k] for k in ('hand_id', 'table_id', 'proposal_index', 'variant')}
    context.update(source_binding_sha256=binding_sha, source_clip_sha256=clip_sha)
    payload = json.dumps(context, ensure_ascii=True).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    return HTML.replace('__CONTEXT__', payload)


def build(binding_path, clip_path):
    b, c = safe_file(binding_path, max_bytes=2_000_000), safe_file(clip_path)
    require(b.resolve() != c.resolve(), 'inputs must be distinct')
    bh, ch = digest(b), digest(c)
    html = render(read_json(b), bh, ch)
    require(digest(b) == bh and digest(c) == ch, 'source changed during rendering')
    return html


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('binding_json'); parser.add_argument('clip_mp4'); parser.add_argument('new_html')
    args = parser.parse_args(argv)
    out, clip = Path(args.new_html), Path(args.clip_mp4)
    require(out.parent.is_dir() and not out.parent.is_symlink() and out.suffix == '.html'
            and not out.exists() and not out.is_symlink(), 'output must be a new HTML file')
    require(out.parent.resolve() == clip.parent.resolve() and clip.name == 'clip.mp4',
            'HTML must be beside clip.mp4')
    require(out.resolve() not in {Path(args.binding_json).resolve(), clip.resolve()}, 'cannot overwrite evidence')
    html = build(args.binding_json, clip)
    with out.open('x', encoding='utf-8') as f:f.write(html)
    print(json.dumps({'html_created':str(out),'source_clip_sha256':digest(clip)}))
    return 0

if __name__ == '__main__':raise SystemExit(main())
