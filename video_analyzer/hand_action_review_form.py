"""Generate a standalone offline HTML editor for *human* visual verdicts.

The browser exports an edited copy of the strictly bound verdict JSON template.
It never writes to the original video/evidence, sends network requests, or
certifies hands/equity/EV. Finalize the downloaded JSON with
hand_action_visual_verdicts.py to revalidate provenance and every verdict.
"""
import argparse
import hashlib
import html
import json
import os
from pathlib import Path
import re
from urllib.parse import quote

from hand_action_pts_evidence import _file, _sha
from hand_action_visual_verdicts import build_template, verified_gallery

SAFE_IMAGE = re.compile(r'action_table_0[1-4]_[0-9]{4}\.png\Z')

CSS = """body{font:16px system-ui,sans-serif;max-width:1180px;margin:1.5rem auto;padding:0 1rem;background:#f7f8fb;color:#202638}
h1{font-size:1.7rem} .notice{background:#fff2cf;border:1px solid #d6ac40;padding:1rem;border-radius:8px}
.controls{display:flex;flex-wrap:wrap;gap:1rem;align-items:center;margin:1rem 0}
article{background:white;border:1px solid #c5cbd4;border-radius:8px;padding:1rem;margin:1rem 0}
article img{max-width:min(100%,620px);max-height:320px;object-fit:contain;display:block;margin:.7rem 0;border:1px solid #888}
label{display:block;margin:.6rem 0}input,select,textarea,button{font:inherit}textarea{width:min(100%,700px);height:4rem;display:block}
input[type=text]{width:min(100%,440px)}code{overflow-wrap:anywhere}small{color:#4b5563}button{padding:.65rem 1rem;cursor:pointer}
.error{color:#a20e17;font-weight:700} .ok{color:#146b2c} .muted{color:#666} .meta{overflow-wrap:anywhere}
"""

JS = r"""'use strict';
const payload = __PAYLOAD__;
const template = payload.template;
const form = structuredClone(template);
const list = document.getElementById('tasks');
const error = document.getElementById('error');
const summary = document.getElementById('summary');
const filter = document.getElementById('table-filter');
const labels = {pending:'Pendente',confirmed_visual:'Confirmado visualmente',rejected_visual:'Rejeitado visualmente',uncertain:'Incerto',unreviewable:'Não revisável'};
const allowed = ['pending','confirmed_visual','rejected_visual','uncertain'];
const elements = [];
function el(tag, text, cls) { const node = document.createElement(tag); if (text !== undefined) node.textContent = String(text); if(cls) node.className=cls; return node; }
function field(container, label, control) { const wrap=el('label');wrap.append(el('span',label),control);container.append(wrap);return control; }
function refresh() {
  const counts = Object.fromEntries(Object.keys(labels).map(k=>[k,0]));
  for(const row of form.rows) counts[row.verdict]++;
  summary.textContent = Object.entries(counts).map(([k,n])=>`${labels[k]}: ${n}`).join(' | ');
  const chosen=filter.value;
  for(const item of elements) item.article.hidden = chosen!=='all' && String(item.row.table_id)!==chosen;
}
for(let i=0;i<form.rows.length;i++) {
  const row=form.rows[i], display=payload.display[i];
  const card=el('article');
  card.append(el('h2',`Mesa ${row.table_id} · ${row.entry_id} · ${row.kind} ${row.item}`));
  card.append(el('p',`Origem: ${display.source_kind} · Estado: ${row.source_status}`));
  card.append(el('p',`Valor anotado: ${JSON.stringify(display.value)} · PTS: ${row.requested_pts_seconds}`,'meta'));
  if(display.image) {
    const img=el('img'); img.src=display.image; img.alt='Imagem auditada para inspeção humana, conteúdo não confirmado'; img.loading='lazy';card.append(img);
    card.append(el('small',`SHA-256: ${row.frame_sha256} · PTS decodificado: ${display.decoded_pts_seconds}`));
  } else card.append(el('p','Sem imagem auditada elegível para revisão.','muted'));
  const select=el('select');
  for(const status of row.verdict==='unreviewable' ? ['unreviewable'] : allowed) {
    const option=el('option',labels[status]);option.value=status;select.append(option);
  }
  select.value=row.verdict; select.disabled=row.verdict==='unreviewable';
  field(card,'Veredito: ',select);
  const reviewer=el('input');reviewer.type='text';reviewer.maxLength=80;reviewer.value=row.reviewer;
  field(card,'Revisor: ',reviewer);
  const notes=el('textarea');notes.maxLength=1000;notes.value=row.notes;
  field(card,'Justificativa (mínimo 8 caracteres): ',notes);
  const confidence=el('input');confidence.type='number';confidence.min='0';confidence.max='1';confidence.step='0.01';
  confidence.value=row.visual_confidence===null?'':String(row.visual_confidence);
  field(card,'Confiança subjetiva (0–1): ',confidence);
  function sync() {
    const active=!['pending','unreviewable'].includes(select.value);
    reviewer.disabled=notes.disabled=confidence.disabled=!active;
    row.verdict=select.value;
    row.reviewer=active?reviewer.value:'';
    row.notes=active?notes.value:'';
    row.visual_confidence=active && confidence.value.trim()!=='' ? Number(confidence.value) : null;
    refresh();
  }
  for(const control of [select,reviewer,notes,confidence]) control.addEventListener('input',sync);
  elements.push({article:card,row});list.append(card);sync();
}
filter.addEventListener('change',refresh);
document.getElementById('export').addEventListener('click',()=>{
  error.textContent='';
  for(let i=0;i<form.rows.length;i++) {
    const row=form.rows[i];
    if(!allowed.includes(row.verdict) && row.verdict!=='unreviewable') {error.textContent=`Estado inválido na linha ${i+1}`;return;}
    if(!['pending','unreviewable'].includes(row.verdict) && (!row.reviewer.trim() || row.notes.trim().length<8 || row.visual_confidence===null || !Number.isFinite(row.visual_confidence) || row.visual_confidence<0 || row.visual_confidence>1)) {
      error.textContent=`Revise nome, justificativa e confiança na linha ${i+1}.`;return;
    }
  }
  const blob=new Blob([JSON.stringify(form,null,2)+'\n'],{type:'application/json'});
  const url=URL.createObjectURL(blob);
  const link=el('a');link.href=url;link.download='visual_review_edited.json';document.body.append(link);link.click();link.remove();
  setTimeout(()=>URL.revokeObjectURL(url),30000);
  error.textContent='JSON exportado. Execute finalize no Python para validar a revisão contra as evidências originais.';
  error.className='ok';
});
refresh();
"""


def _display(gallery, template, evidence_dir, output_file):
    lookup = {}
    for entry in gallery['entries']:
        for link in entry['links']:
            key = (entry['entry_id'], link['kind'], link['item'])
            if key in lookup:
                raise ValueError('Duplicate visual link')
            lookup[key] = link
    relative = Path(os.path.relpath(Path(evidence_dir).resolve(), Path(output_file).parent.resolve()))
    result = []
    for row in template['rows']:
        link = lookup[(row['entry_id'], row['kind'], row['item'])]
        frame = link['frame'] if row['verdict'] == 'pending' else None
        image = None
        if frame:
            name = frame['filename']
            if not isinstance(name, str) or not SAFE_IMAGE.fullmatch(name):
                raise ValueError('Unsafe image filename')
            image = quote((relative / name).as_posix(), safe='/.-_')
        result.append({'source_kind': link['source_kind'], 'value': link['value'],
                       'image': image,
                       'decoded_pts_seconds': frame['decoded_pts_seconds'] if frame else None})
    return result


def render(template, gallery, gallery_sha, evidence_dir, output_file):
    """Return self-contained HTML with CSP; no external JS, fonts, or calls."""
    if template != build_template(gallery, gallery_sha):
        raise ValueError('Template differs from verified gallery')
    display = _display(gallery, template, evidence_dir, output_file)
    payload = json.dumps({'template': template, 'display': display}, ensure_ascii=True,
                         allow_nan=False, separators=(',', ':'))
    # JSON is embedded in an executable script: escape HTML tag delimiters.
    payload = payload.replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    script = JS.replace('__PAYLOAD__', payload)
    script_sha = hashlib.sha256(script.encode('utf-8')).digest()
    import base64
    csp = "default-src 'none'; script-src 'sha256-" + base64.b64encode(script_sha).decode() + "'; style-src 'unsafe-inline'; img-src 'self' file: data:; object-src 'none'; connect-src 'none'; base-uri 'none'; form-action 'none'"
    return ('<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta http-equiv="Content-Security-Policy" content="' + html.escape(csp, quote=True) + '">'
            '<title>PLO Trainee — formulário de revisão visual</title><style>' + CSS + '</style></head><body>'
            '<h1>PLO Trainee — revisão visual offline</h1>'
            '<p class="notice">Somente vídeos gravados. Vereditos humanos sobre imagens não confirmam mãos completas, cartas ocultas, equity, EV ou erros estratégicos. '
            'Nenhum dado é enviado pela internet. O JSON exportado precisa ser validado pelo comando <code>finalize</code>.</p>'
            '<div class="controls"><label>Mesa: <select id="table-filter"><option value="all">Todas</option>'
            + ''.join(f'<option value="{n}">{n}</option>' for n in range(1, 5))
            + '</select></label><button type="button" id="export">Exportar JSON de revisão</button></div>'
            '<p id="summary" aria-live="polite"></p><p id="error" role="status"></p><main id="tasks"></main>'
            '<script>' + script + '</script></body></html>\n')


def export(video, navigation, review, evidence_dir, gallery_dir, output_html, *, regions_json=None):
    """Verify original evidence, then create a *new* offline HTML file."""
    output = Path(output_html)
    if output.suffix.lower() != '.html' or output.exists() or output.is_symlink():
        raise ValueError('Output must be a new HTML file')
    evidence, gallery_root = Path(evidence_dir), Path(gallery_dir)
    if (output.resolve().is_relative_to(evidence.resolve())
            or output.resolve().is_relative_to(gallery_root.resolve())):
        raise ValueError('Output must be outside evidence/gallery directories')
    sources = [_file(p) for p in (video, navigation, review)]
    sources.extend([_file(evidence / 'action_pts_evidence.json'),
                    _file(gallery_root / 'review_gallery.json')])
    if regions_json is not None:
        sources.append(_file(regions_json))
    if output.resolve() in {p.resolve() for p in sources}:
        raise ValueError('Cannot overwrite input')
    before = [_sha(p) for p in sources]
    checked, digest = verified_gallery(video, navigation, review, evidence_dir,
                                      gallery_dir, regions_json)
    template = build_template(checked, digest)
    page = render(template, checked, digest, evidence_dir, output)
    if any(_sha(p) != h for p, h in zip(sources, before)):
        raise ValueError('Source changed during HTML generation')
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as stream:
        stream.write(page)
    return {'output': str(output), 'rows': len(template['rows']),
            'eligible': sum(row['verdict'] == 'pending' for row in template['rows']),
            'requires_backend_finalization': True}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('video', 'navigation', 'review', 'evidence_dir', 'gallery_dir', 'output_html'):
        parser.add_argument(name)
    parser.add_argument('--regions-json')
    args = parser.parse_args(argv)
    print(json.dumps(export(args.video, args.navigation, args.review, args.evidence_dir,
                            args.gallery_dir, args.output_html, regions_json=args.regions_json)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
