"""Generate a standalone, network-free browser editor for manual PLO observations.

Loads an existing session_review.json through a user-selected local file,
exports manual_annotations.json for offline_human_observation_review.py.
The browser does not authenticate reviewers or verify OCR/EV.
Usage: python video_analyzer/offline_manual_review_editor.py review_editor.html
"""
from __future__ import annotations
import argparse
import base64
import hashlib
from html import escape
from pathlib import Path

EDITOR_JS = r"""'use strict';
const $ = id => document.getElementById(id);
const MAX_BYTES = 4 * 1024 * 1024;
const ACTIONS = ['fold','call','raise'];
const OUTCOMES = ['pending','confirmed','corrected','inconclusive'];
let session = null, sessionSha = null, controls = [];
function message(s, bad=false) {
  $('message').textContent = s;
  $('message').className = bad ? 'error' : 'notice';
}
function fail(s) { throw new Error(s); }
function validTime(t) { return typeof t === 'number' && Number.isFinite(t) && t >= 0; }
function validId(s,n) { return typeof s === 'string' && s.length > 0 && s.length <= n && !/[\x00-\x1f\x7f]/.test(s); }
function hex(b) { return Array.from(new Uint8Array(b), x=>x.toString(16).padStart(2,'0')).join(''); }
function validatePacket(p) {
  if (!p || typeof p !== 'object' || Array.isArray(p) ||
    p.schema_version !== 1 || p.analysis_status !== 'offline_read_only_human_review_packet' ||
    p.human_review_recorded !== false || p.video_evidence_independently_verified !== false ||
    p.range_assumptions_verified !== false || p.decision_quality_verified !== false ||
    p.automatic_clip_selection_authorized !== false || p.action_recommendation_authorized !== false ||
    p.clip_media_hashes_rechecked !== true || p.ffprobe_media_checked !== true ||
    !Array.isArray(p.decisions) || p.decisions.length < 1 || p.decisions.length > 32 ||
    p.decision_count !== p.decisions.length) fail('Relatório de origem incompatível.');
  const keys = new Set();
  for (const r of p.decisions) {
    if (!r || !Number.isInteger(r.table_id) || r.table_id < 1 || r.table_id > 4 ||
      !validId(r.hand_id,64) || !validId(r.decision_id,1000) ||
      !['PLO5','PLO6'].includes(r.game_type) || !ACTIONS.includes(r.observed_action) ||
      r.human_review_status !== 'pending' || r.model_conditional_only !== true ||
      r.decision_quality_verified !== false ||
      !Array.isArray(r.candidate_window_seconds) || r.candidate_window_seconds.length !== 2 ||
      !Array.isArray(r.clip_window_seconds) || r.clip_window_seconds.length !== 2 ||
      !validTime(r.action_pts_seconds)) fail('Decisão inválida.');
    const [hs,he] = r.candidate_window_seconds, [cs,ce] = r.clip_window_seconds;
    if (![hs,he,cs,ce].every(validTime) ||
      !(cs <= hs && hs <= r.action_pts_seconds && r.action_pts_seconds <= he && he <= ce && hs < he))
      fail('Timestamps inválidos.');
    const key = JSON.stringify([r.table_id,r.hand_id,r.decision_id]);
    if (keys.has(key)) fail('Decisão duplicada.');
    keys.add(key);
  }
}
function el(tag, cls, value) {
  const n=document.createElement(tag);
  if (cls) n.className=cls;
  if (value !== undefined) n.textContent=String(value);
  return n;
}
function field(parent, label, control) {
  const l=el('label','field'); l.append(el('span','',label),control); parent.append(l);
}
function render() {
  const area=$('decisions'); area.replaceChildren(); controls=[];
  session.decisions.forEach((r,i)=>{
    const card=el('article','card');
    card.append(el('h2','',`#${i+1} · Mesa ${r.table_id} · ${r.game_type} · ${r.hand_id}`));
    card.append(el('p','muted',`Decisão ${r.decision_id} · ${r.observed_action} aos ${r.action_pts_seconds}s · Mão ${r.candidate_window_seconds[0]}–${r.candidate_window_seconds[1]}s`));
    const status=el('select');
    OUTCOMES.forEach(x=>{const o=el('option','',x);o.value=x;status.append(o);});
    field(card,'Resultado da revisão',status);
    const correction=el('div','correction'), action=el('select');
    ACTIONS.forEach(x=>{const o=el('option','',x);o.value=x;action.append(o);});
    action.value=r.observed_action; field(correction,'Ação corrigida',action);
    const time=el('input'); time.type='number';time.min='0';time.step='any';time.value=String(r.action_pts_seconds);
    field(correction,'Timestamp corrigido (segundos)',time);card.append(correction);
    const note=el('textarea');note.maxLength=1000;note.rows=3;
    field(card,'Justificativa / observação',note);
    const toggle=()=>{correction.hidden=status.value!=='corrected';};
    status.addEventListener('change',toggle);toggle();
    area.append(card);controls.push({r,status,action,time,note});
  });
  $('export').disabled=false;
  $('sessionInfo').textContent=`${session.decision_count} decisões · SHA-256 ${sessionSha}`;
}
async function importSession(file) {
  session=null;sessionSha=null;controls=[];
  $('export').disabled=true;$('decisions').replaceChildren();
  if (!file || file.size<1 || file.size>MAX_BYTES) fail('Arquivo ausente ou maior que 4 MiB.');
  if (!globalThis.crypto || !crypto.subtle) fail('SHA-256 indisponível neste navegador; exportação bloqueada.');
  const bytes=await file.arrayBuffer();
  const digest=await crypto.subtle.digest('SHA-256',bytes);
  const p=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(bytes));
  validatePacket(p);session=p;sessionSha=hex(digest);render();
  message('Relatório carregado; anotações ainda não exportadas.');
}
function collect() {
  if (!session || !/^[0-9a-f]{64}$/.test(sessionSha)) fail('Carregue um relatório válido.');
  const alias=$('alias').value.trim();
  if (!/^[A-Za-z0-9][A-Za-z0-9_.-]{2,47}$/.test(alias)) fail('Identificador inválido (3–48 caracteres).');
  const entries=[];
  for (const {r,status,action,time,note} of controls) {
    const outcome=status.value;if(outcome==='pending')continue;
    const memo=note.value;
    if (memo.length>1000 || /[\x00-\x08\x0b\x0c\x0e-\x1f]/.test(memo)) fail('Nota inválida.');
    let correctedAction=null,correctedTime=null;
    if (outcome==='corrected') {
      correctedAction=action.value;
      if (!ACTIONS.includes(correctedAction) || time.value.trim()==='') fail('Informe ação e timestamp.');
      correctedTime=Number(time.value);
      const [hs,he]=r.candidate_window_seconds;
      if (!validTime(correctedTime) || correctedTime<hs || correctedTime>he ||
        (correctedAction===r.observed_action && correctedTime===r.action_pts_seconds))
        fail('Correção deve alterar observação dentro da mão.');
      if(memo.trim().length<10)fail('Correção exige justificativa de 10 caracteres.');
    } else if(outcome==='inconclusive') {
      if(memo.trim().length<10)fail('Inconclusivo exige justificativa de 10 caracteres.');
    } else if(outcome!=='confirmed')fail('Resultado desconhecido.');
    entries.push({table_id:r.table_id,hand_id:r.hand_id,decision_id:r.decision_id,
      outcome,corrected_observed_action:correctedAction,corrected_action_pts_seconds:correctedTime,note:memo});
  }
  if(!entries.length)fail('Selecione ao menos uma decisão.');
  return {schema_version:1,source_session_review_sha256:sessionSha,reviewer_alias:alias,entries};
}
function download() {
  const blob=new Blob([JSON.stringify(collect(),null,2)+'\n'],{type:'application/json;charset=utf-8'});
  const url=URL.createObjectURL(blob),a=el('a');
  a.href=url;a.download='manual_annotations.json';document.body.append(a);a.click();a.remove();
  setTimeout(()=>URL.revokeObjectURL(url),2000);
  message('JSON exportado localmente; validação Python ainda obrigatória.');
}
$('sessionFile').addEventListener('change',async e=>{
  try{await importSession(e.target.files[0]);}catch(err){message('Falha: '+err.message,true);}
});
$('export').addEventListener('click',()=>{
  try{download();}catch(err){message('Exportação bloqueada: '+err.message,true);}
});
"""

def render_editor():
    digest = base64.b64encode(hashlib.sha256(EDITOR_JS.encode('utf-8')).digest()).decode('ascii')
    csp = ("default-src 'none'; script-src 'sha256-" + digest +
           "'; style-src 'unsafe-inline'; connect-src 'none'; media-src 'none'; "
           "object-src 'none'; frame-src 'none'; base-uri 'none'; form-action 'none'")
    return ('''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="''' + escape(csp, quote=True) + '''">
<title>PLO Trainee — editor de revisão offline</title>
<style>
:root{color-scheme:dark}body{font:16px system-ui,sans-serif;max-width:1000px;margin:2rem auto;padding:0 1rem;background:#111827;color:#f9fafb}
h1{font-size:1.8rem}.card{background:#1f2937;border:1px solid #4b5563;border-radius:12px;padding:1rem;margin:1rem 0}
.field{display:block;margin:.7rem 0}.field span{display:block;margin-bottom:.35rem;font-weight:600}
input,select,textarea,button{box-sizing:border-box;font:inherit;padding:.55rem;border:1px solid #6b7280;border-radius:7px;background:#0f172a;color:#fff;max-width:100%;width:100%}
button{background:#2563eb;border:0;cursor:pointer;font-weight:700;padding:.8rem}button:disabled{opacity:.4;cursor:not-allowed}
.correction{border-left:3px solid #60a5fa;padding-left:1rem;margin:1rem 0}.correction[hidden]{display:none}
.muted{color:#d1d5db;overflow-wrap:anywhere}.notice{color:#86efac}.error{color:#fca5a5}
</style></head><body>
<h1>PLO Trainee — revisão manual offline</h1>
<p class="muted">Importe session_review.json. Confirme, corrija ou marque decisões inconclusivas e exporte manual_annotations.json. Sem rede, sem vídeo ao vivo e sem recomendação de apostas. OCR e EV não são autenticados.</p>
<div class="card"><label class="field"><span>Arquivo session_review.json</span><input id="sessionFile" type="file" accept=".json,application/json"></label>
<label class="field"><span>Identificador do revisor (não autenticado)</span><input id="alias" maxlength="48" placeholder="revisor_local"></label>
<p id="sessionInfo" class="muted"></p><p id="message" role="status" aria-live="polite"></p></div>
<main id="decisions"></main><button id="export" disabled>Exportar manual_annotations.json</button>
<p class="muted">Execute offline_human_observation_review.py para revalidar o arquivo e gerar um novo relatório. Correções invalidam EV dependente até recálculo.</p>
<script>''' + EDITOR_JS + '''</script></body></html>\n''')

def build(output):
    output = Path(output)
    if output.suffix.lower() != '.html' or output.exists() or output.is_symlink():
        raise ValueError('Use um novo arquivo .html; não sobrescrever')
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as stream:
        stream.write(render_editor())
    return output

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('new_editor_html')
    args = parser.parse_args(argv)
    print(build(args.new_editor_html))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
