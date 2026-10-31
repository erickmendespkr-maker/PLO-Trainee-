"""Generate a self-contained offline review form for recorded PLO5/PLO6 evidence.

python offline_street_review_form.py VIDEO OBSERVATIONS STREET_DIR OUTPUT_DIR

The browser exports manual_review.json; offline_street_human_review.py remains the
validator. Nothing is auto-confirmed and no equity/EV calculation is authorized.
"""
import argparse
import json
import os
from pathlib import Path
import tempfile

import offline_ev_table_crop as media
import offline_street_evidence as street

PAGE = 'street_review_form.html'


def safe_json(data):
    return (json.dumps(data, ensure_ascii=True, allow_nan=False, separators=(',', ':'))
            .replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026'))


safe_json_for_html = safe_json


def page(report, sha):
    payload = {'schema_version': 1, 'status': 'manual_offline_street_review',
               'source_street_report_sha256': sha, 'variant': report['variant'],
               'hands': report['hands']}
    return '''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'none'; img-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'">
<title>PLO Trainee — revisão offline</title><style>
:root{font-family:system-ui,Arial,sans-serif;color-scheme:light}
body{max-width:1000px;margin:auto;padding:1rem;background:#f5f7fb;color:#15243b}
header,section{background:white;border:1px solid #d5deea;border-radius:12px;padding:1rem;margin:1rem 0}
h1{font-size:1.6rem}h2{font-size:1.2rem}.warning{padding:.8rem;background:#fff2d6;border-left:4px solid #a75e00}
.event{display:grid;grid-template-columns:1fr 1fr;gap:.8rem;padding:.8rem 0;border-top:1px solid #d5deea}
.event p{overflow-wrap:anywhere}label{display:grid;gap:.25rem;font-weight:600;margin:.3rem 0}
input,select,textarea{font:inherit;padding:.5rem;border:1px solid #8190a4;border-radius:5px;min-width:0;width:100%;box-sizing:border-box}
button{background:#214c91;color:white;border:0;border-radius:6px;padding:.7rem 1rem;cursor:pointer}
:focus-visible{outline:3px solid #efb128}#message{white-space:pre-wrap;font-weight:600}
.error{color:#a12020}.ok{color:#166c39}small{color:#45566d}
@media(max-width:650px){.event{grid-template-columns:1fr}}
</style></head><body><header><h1>Revisão humana de mãos gravadas</h1>
<p class="warning">Nenhuma observação começa confirmada. OCR e confiança são propostas não calibradas. Nenhuma autorização de equity ou EV. Sem conexão ou apostas.</p>
<p>Exporte o JSON e valide com <code>offline_street_human_review.py</code> usando os arquivos originais.</p>
<label>Identificação do revisor (letras, números, _ e -; até 64)
<input id="reviewer" maxlength="64" autocomplete="off" placeholder="revisor_1"></label>
<p id="progress" aria-live="polite"></p></header><main id="hands"></main>
<section><button id="export" type="button">Validar e baixar manual_review.json</button>
<p id="message" role="status" aria-live="polite"></p></section>
<script type="application/json" id="ledger">''' + safe_json(payload) + '''</script><script>
'use strict';(() => {
const src=JSON.parse(document.getElementById('ledger').textContent);
const root=document.getElementById('hands'), controls=[];
const el=(tag,txt)=>{const x=document.createElement(tag);if(txt!==undefined)x.textContent=txt;return x;};
const fmt=x=>Array.isArray(x)?x.join(' '):String(x);
const progress=()=>{document.getElementById('progress').textContent=controls.filter(c=>c.choice.value).length+' de '+controls.length+' observações revisadas explicitamente';};
for(const hand of src.hands){
 const sec=el('section');sec.append(el('h2','Mesa '+hand.table_id+' · mão '+hand.hand_id));
 sec.append(el('p','Intervalo '+hand.start_seconds+'–'+hand.end_seconds+' s · alertas: '+(hand.review_flags.join(', ')||'nenhum')));
 const hc=[];let idx=0;
 for(const [street,events] of Object.entries(hand.streets))for(const event of events){
  const row=el('div');row.className='event';const info=el('div');
  info.append(el('h3','Evento '+idx+' · '+street+' · '+event.kind),el('p','Proposta: '+fmt(event.value)),
              el('small','Tempo '+event.timestamp_seconds+' s · '+event.origin+' · confiança NÃO calibrada '+event.confidence));
  const fields=el('div');const choiceLabel=el('label','Decisão obrigatória'),choice=el('select');
  for(const [v,t] of [['','Escolha'],['confirm','Confirmar'],['correct','Corrigir'],['reject','Rejeitar']]){
   const opt=el('option',t);opt.value=v;choice.append(opt);
  }
  choiceLabel.append(choice);
  const valueLabel=el('label','Novo valor (cartas separadas por espaço ou vírgula)'),value=el('input');
  value.maxLength=120;valueLabel.append(value);
  const reasonLabel=el('label','Justificativa da correção/rejeição'),reason=el('textarea');
  reason.maxLength=300;reasonLabel.append(reason);
  const sync=()=>{valueLabel.hidden=choice.value!=='correct';reasonLabel.hidden=!['correct','reject'].includes(choice.value);progress();};
  choice.addEventListener('change',sync);sync();fields.append(choiceLabel,valueLabel,reasonLabel);
  row.append(info,fields);sec.append(row);const c={choice,value,reason,event,street,index:idx};
  hc.push(c);controls.push(c);idx++;
 }
 sec._review={hand,controls:hc};root.append(sec);
}
progress();
const fail=s=>{throw Error(s);};
const parse=c=>{
 const raw=c.value.value.trim();
 if(['board','hero_cards'].includes(c.event.kind)){
  const cards=raw.toUpperCase().split(/[\\s,]+/).filter(Boolean);
  const n=c.event.kind==='hero_cards'?(src.variant==='PLO5'?5:6):({flop:3,turn:4,river:5}[c.street]);
  if(cards.length!==n||new Set(cards).size!==n||!cards.every(x=>/^[2-9TJQKA][CDHS]$/.test(x)))fail('Cartas inválidas no evento '+c.index);
  return cards;
 }
 if(!raw||raw.length>120||[...raw].some(x=>x.charCodeAt(0)<32))fail('Texto inválido no evento '+c.index);
 return raw;
};
document.getElementById('export').addEventListener('click',()=>{
 const message=document.getElementById('message');message.className='';message.textContent='';
 try{
  const reviewer=document.getElementById('reviewer').value.trim();
  if(!/^[A-Za-z0-9_-]{1,64}$/.test(reviewer))fail('Identificação de revisor inválida');
  const hands=[];
  for(const sec of root.children){
   const {hand,controls}=sec._review,decisions=[];
   for(const c of controls){
    const action=c.choice.value,reason=c.reason.value.trim();
    if(!['confirm','correct','reject'].includes(action))fail('Revise explicitamente o evento '+c.index+' da mão '+hand.hand_id);
    if(reason.length>300||[...reason].some(x=>x.charCodeAt(0)<32))fail('Justificativa inválida no evento '+c.index);
    let value=null;
    if(action==='correct'){
     if(!reason)fail('Correção exige justificativa no evento '+c.index);
     value=parse(c);
     if(JSON.stringify(value)===JSON.stringify(c.event.value))fail('Correção precisa alterar o valor no evento '+c.index);
    }
    if(action==='reject'&&!reason)fail('Rejeição exige justificativa no evento '+c.index);
    decisions.push({event_index:c.index,decision:action,value,reason:action==='confirm'?'':reason});
   }
   hands.push({table_id:hand.table_id,hand_id:hand.hand_id,decisions});
  }
  const result={schema_version:1,status:src.status,source_street_report_sha256:src.source_street_report_sha256,reviewer_label:reviewer,hands};
  const url=URL.createObjectURL(new Blob([JSON.stringify(result,null,2)+'\\n'],{type:'application/json'}));
  const a=el('a');a.href=url;a.download='manual_review.json';document.body.append(a);a.click();a.remove();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
  message.className='ok';message.textContent='JSON gerado. Execute o validador Python antes de usar qualquer dado.';
 }catch(err){message.className='error';message.textContent=err.message;}
});
})();
</script></body></html>'''


def export(video, observations, street_dir, output_dir):
    video, observations, street_dir, output_dir = map(Path, (video, observations, street_dir, output_dir))
    media.check(street_dir.is_dir() and not street_dir.is_symlink() and
                output_dir.is_dir() and not output_dir.is_symlink(), 'unsafe directories')
    media.check(len({p.resolve() for p in (video, observations, street_dir, output_dir)}) == 4,
                'paths must differ')
    target = output_dir / PAGE
    media.check(not target.exists() and not target.is_symlink(), 'output collision')
    ledger = street_dir / street.REPORT
    stored = media.read_json(ledger)
    with tempfile.TemporaryDirectory(prefix='plo_form_check_', dir=output_dir) as folder:
        expected, sources = street.validate(video, observations, folder)
    media.check(stored == expected, 'street report altered or mismatched')
    sources = tuple(sources) + ((ledger, media.digest(ledger)),)
    with tempfile.TemporaryDirectory(prefix='plo_form_write_', dir=output_dir) as folder:
        tmp = Path(folder) / PAGE
        tmp.write_text(page(expected, sources[-1][1]), encoding='utf-8')
        media.check(all(media.digest(p) == sha for p, sha in sources), 'source changed')
        media.check(not target.exists() and not target.is_symlink(), 'output collision')
        os.link(tmp, target)
    return target


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('video', 'observations', 'street_dir', 'output_dir'):
        p.add_argument(name)
    args = p.parse_args(argv)
    print(export(args.video, args.observations, args.street_dir, args.output_dir))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())