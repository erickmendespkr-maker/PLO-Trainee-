"""Build a self-contained, offline ROI editor for human-declared PLO table geometry.

Usage: python offline_table_roi_editor.py FRAME.png TEMPLATE.json NEW_EDITOR.html

The frame must be extracted from an authorized recording. All edits remain
human-declared and unverified; the browser only downloads a revised template.
No OCR is confirmed and no equity/EV is enabled by this tool.
"""
from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path

from PIL import Image
import offline_table_roi_sampler as sampler
import offline_reviewed_hand_math_queue as queue

MAX_FRAME_BYTES = 16 * 1024 * 1024

PAGE = r'''<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'">
<title>PLO Trainee — editor offline de regiões</title>
<style>
:root{font:15px system-ui,Arial,sans-serif;color-scheme:dark;background:#111827;color:#e5e7eb}
*{box-sizing:border-box}body{margin:0}header{padding:16px 22px;border-bottom:1px solid #374151;display:flex;gap:16px;align-items:center;justify-content:space-between;flex-wrap:wrap}
h1{font-size:19px;margin:0}small,.muted{color:#9ca3af}main{display:grid;grid-template-columns:minmax(0,1fr) 290px;gap:18px;padding:18px}
.viewer{min-width:0}canvas{display:block;width:100%;height:auto;background:#030712;border:1px solid #374151;touch-action:none;cursor:crosshair;border-radius:10px}
.panel{background:#1f2937;border:1px solid #374151;border-radius:10px;padding:15px;align-self:start}
label{display:block;font-size:13px;margin:12px 0 5px}select,button{font:inherit;background:#111827;color:#fff;border:1px solid #4b5563;border-radius:7px;padding:9px;width:100%}
button{cursor:pointer;margin-top:10px}button.primary{background:#0f766e;border-color:#14b8a6;font-weight:650}button:disabled{opacity:.4;cursor:not-allowed}
.info{font-size:13px;line-height:1.5;color:#d1d5db}.warning{color:#fbbf24;font-weight:650}
#coordinates{font-family:monospace;word-break:break-word}footer{padding:0 18px 20px;color:#9ca3af;font-size:13px}
@media(max-width:780px){main{grid-template-columns:1fr}}
</style></head><body>
<header><div><h1>PLO Trainee · ajuste visual de regiões</h1><small>Editor 100% local — sem envio de imagens ou dados</small></div><strong class="warning">NÃO VERIFICADO · revisão humana obrigatória</strong></header>
<main><section class="viewer"><canvas id="frame" aria-label="Quadro e regiões editáveis"></canvas><p class="info">Selecione mesa ou campo. Arraste dentro do contorno para mover; arraste o quadrado no canto inferior direito para redimensionar. A mesa move seus campos junto.</p></section>
<aside class="panel"><label for="table">Mesa</label><select id="table"></select><label for="field">Região a editar</label><select id="field"></select><p class="info" id="coordinates"></p>
<button id="undo" type="button">Desfazer</button><button id="reset" type="button">Restaurar original</button><button id="download" type="button" class="primary">Baixar template JSON revisado</button>
<p class="info warning">O download não confirma cartas, ações, timestamps ou decisões. Confira a imagem e utilize o fluxo de revisão antes de Monte Carlo.</p><p id="message" role="status" class="info"></p></aside></main>
<footer>Regiões normalizadas relativas à mesa. Arquivo compatível com offline_table_roi_sampler.py. Sem chamadas de rede.</footer>
<script>
'use strict';
const original = __TEMPLATE__;
const imageData = '__IMAGE__';
const width = __WIDTH__, height = __HEIGHT__;
let state = structuredClone(original), selectedTable = 0, selectedField = -1, drag = null, history = [];
const canvas = document.getElementById('frame'), ctx = canvas.getContext('2d');
const tableSelect = document.getElementById('table'), fieldSelect = document.getElementById('field');
const message = document.getElementById('message');
canvas.width=width;canvas.height=height;
const image = new Image();image.src=imageData;image.onload=render;
const clone = value => structuredClone(value);
const inside = (r,x,y) => x>=r.x && y>=r.y && x<=r.x+r.w && y<=r.y+r.h;
const overlaps = (a,b) => Math.min(a.x+a.w,b.x+b.w)>Math.max(a.x,b.x)+1e-9 && Math.min(a.y+a.h,b.y+b.h)>Math.max(a.y,b.y)+1e-9;
function globalRect(t,f){return {x:t.x+t.w*f.x,y:t.y+t.h*f.y,w:t.w*f.w,h:t.h*f.h};}
function valid(){
  const tables=state.tables;
  for(let i=0;i<tables.length;i++){
    const t=tables[i].roi;
    if(!validRect(t) || Math.round(t.w*width)<12 || Math.round(t.h*height)<12)return false;
    for(let j=0;j<i;j++)if(overlaps(t,tables[j].roi))return false;
    for(const f of tables[i].fields){const g=globalRect(t,f.roi);if(!validRect(f.roi)||Math.round(g.w*width)<12||Math.round(g.h*height)<12)return false;}
  }return true;
}
function validRect(r){return [r.x,r.y,r.w,r.h].every(Number.isFinite)&&r.x>=0&&r.y>=0&&r.w>0&&r.h>0&&r.x+r.w<=1+1e-9&&r.y+r.h<=1+1e-9;}
function selectedRect(){const table=state.tables[selectedTable];return selectedField<0?table.roi:globalRect(table.roi,table.fields[selectedField].roi);}
function controls(){
 tableSelect.replaceChildren();state.tables.forEach((t,i)=>{const o=new Option(t.table_id,t.table_id);o.value=i;tableSelect.add(o);});tableSelect.value=selectedTable;
 fieldSelect.replaceChildren();fieldSelect.add(new Option('Mesa inteira','-1'));
 state.tables[selectedTable].fields.forEach((f,i)=>fieldSelect.add(new Option(f.field+(f.slot===null?'':':'+f.slot),String(i))));fieldSelect.value=selectedField;
 document.getElementById('undo').disabled=!history.length;
}
function drawRect(r,color,label,active){
 const x=r.x*width,y=r.y*height,w=r.w*width,h=r.h*height;
 ctx.lineWidth=active?4:2;ctx.strokeStyle=color;ctx.strokeRect(x,y,w,h);
 ctx.font='bold 13px system-ui';const labelWidth=Math.min(width-x,ctx.measureText(label).width+10);
 ctx.fillStyle='#111827';ctx.fillRect(x,Math.max(0,y-19),labelWidth,19);ctx.fillStyle=color;ctx.fillText(label,x+4,Math.max(13,y-5));
 if(active){ctx.fillStyle=color;ctx.fillRect(x+w-7,y+h-7,14,14);}
}
function render(){
 if(!image.complete || !image.naturalWidth)return;
 ctx.clearRect(0,0,width,height);ctx.drawImage(image,0,0,width,height);
 state.tables.forEach((table,ti)=>{drawRect(table.roi,'#fbbf24',table.table_id,ti===selectedTable&&selectedField<0);
 table.fields.forEach((field,fi)=>drawRect(globalRect(table.roi,field.roi),'#2dd4bf',field.field+(field.slot===null?'':':'+field.slot),ti===selectedTable&&fi===selectedField));});
 const r=selectedRect();document.getElementById('coordinates').textContent=['x','y','w','h'].map(k=>k+'='+r[k].toFixed(5)).join(' · ');
 controls();
}
function point(e){const box=canvas.getBoundingClientRect();return {x:(e.clientX-box.left)/box.width,y:(e.clientY-box.top)/box.height};}
function choose(p){
 for(let ti=state.tables.length-1;ti>=0;ti--){const table=state.tables[ti];
  for(let fi=table.fields.length-1;fi>=0;fi--)if(inside(globalRect(table.roi,table.fields[fi].roi),p.x,p.y))return [ti,fi];
  if(inside(table.roi,p.x,p.y))return [ti,-1];
 }return null;
}
canvas.addEventListener('pointerdown',e=>{
 const p=point(e),r=selectedRect();let hit=inside(r,p.x,p.y), handle=Math.abs(p.x-r.x-r.w)*width<16&&Math.abs(p.y-r.y-r.h)*height<16;
 if(!hit&&!handle){const found=choose(p);if(!found)return;[selectedTable,selectedField]=found;render();hit=true;handle=false;}
 drag={start:p,before:clone(state),mode:handle?'resize':'move'};canvas.setPointerCapture(e.pointerId);
});
canvas.addEventListener('pointermove',e=>{
 if(!drag)return;const p=point(e),dx=p.x-drag.start.x,dy=p.y-drag.start.y;
 state=clone(drag.before);const table=state.tables[selectedTable];let r=selectedField<0?table.roi:table.fields[selectedField].roi;
 const scaleX=selectedField<0?1:table.roi.w,scaleY=selectedField<0?1:table.roi.h;
 if(drag.mode==='move'){r.x+=dx/scaleX;r.y+=dy/scaleY;}else{r.w+=dx/scaleX;r.h+=dy/scaleY;}
 if(!valid()){state=clone(drag.before);message.textContent='Limite inválido: fora da imagem, sobreposição ou região pequena demais.';}else message.textContent='Alteração visual ainda não confirmada.';
 render();
});
function finish(){if(!drag)return;if(JSON.stringify(state)!==JSON.stringify(drag.before))history.push(drag.before);drag=null;render();}
canvas.addEventListener('pointerup',finish);canvas.addEventListener('pointercancel',()=>{if(drag)state=drag.before;drag=null;render();});
tableSelect.addEventListener('change',()=>{selectedTable=Number(tableSelect.value);selectedField=-1;render();});
fieldSelect.addEventListener('change',()=>{selectedField=Number(fieldSelect.value);render();});
document.getElementById('undo').onclick=()=>{if(history.length){state=history.pop();render();}};
document.getElementById('reset').onclick=()=>{history.push(clone(state));state=clone(original);render();};
document.getElementById('download').onclick=()=>{
 if(!valid()){message.textContent='Template inválido; download bloqueado.';return;}
 const blob=new Blob([JSON.stringify(state,null,2)+'\n'],{type:'application/json'});
 const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='plo_roi_template_revisado.json';a.click();URL.revokeObjectURL(url);
 message.textContent='Template salvo localmente. Revisão de cartas e ações ainda necessária.';
};
render();
</script></body></html>'''


def create(frame: Path, template: dict) -> str:
    queue.require(frame.is_file() and not frame.is_symlink() and
                  frame.suffix.lower() == '.png' and
                  0 < frame.stat().st_size <= MAX_FRAME_BYTES, 'invalid local PNG frame')
    with Image.open(frame) as img:
        queue.require(img.format == 'PNG', 'input must be PNG')
        width, height = img.size
        img.verify()
    queue.require(64 <= width <= 8192 and 64 <= height <= 8192,
                  'invalid frame dimensions')
    clips = {f'frame-{i}': {'table_id': t['table_id']}
             for i, t in enumerate(template.get('tables', []))
             if isinstance(t, dict) and isinstance(t.get('table_id'), str)}
    sampler.validate_template(template, clips, width, height)
    encoded = base64.b64encode(frame.read_bytes()).decode('ascii')
    safe_json = json.dumps(template, ensure_ascii=True, allow_nan=False).replace('<', '\\u003c')
    return (PAGE.replace('__TEMPLATE__', safe_json)
            .replace('__IMAGE__', 'data:image/png;base64,' + encoded)
            .replace('__WIDTH__', str(width)).replace('__HEIGHT__', str(height)))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('frame_png')
    parser.add_argument('template_json')
    parser.add_argument('new_editor_html')
    args = parser.parse_args(argv)
    frame, template_path, output = map(Path, (args.frame_png, args.template_json, args.new_editor_html))
    queue.require(len({p.resolve() for p in (frame, template_path, output)}) == 3 and
                  output.suffix.lower() == '.html' and output.parent.is_dir() and
                  not output.parent.is_symlink() and not output.exists() and
                  not output.is_symlink(), 'output must be a distinct new HTML file')
    before = [queue.digest(p) for p in (frame, template_path)]
    html = create(frame, queue.read(template_path))
    queue.require(before == [queue.digest(p) for p in (frame, template_path)],
                  'input changed during editor generation')
    with output.open('x', encoding='utf-8') as stream:
        stream.write(html)
    print(json.dumps({'editor': str(output), 'offline': True,
                      'human_review_required': True, 'eligible_for_equity': 0}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
