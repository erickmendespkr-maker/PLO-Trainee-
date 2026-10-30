"""Build a standalone offline, human-only OCR review page from verified frames.

Usage: python offline_ocr_frame_review_page.py FRAME_DIRECTORY WORKSHEET.json NEW_PAGE.html

The browser exports a *draft*, never queue-ready annotations. OCR confidence is
uncalibrated; an exact-time image must exist for a human 'accept' choice.
No network, poker integration, equity, EV or automatic confirmations.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
from pathlib import Path
import re

from PIL import Image

SHA = re.compile(r'[0-9a-f]{64}\Z')
FRAME = re.compile(r'frame_[0-9]{3}\.png\Z')
MAX_FRAMES = 12
MAX_IMAGE_BYTES = 64 * 1024 * 1024
MAX_JSON_BYTES = 4 * 1024 * 1024
MATCH_TOLERANCE_SECONDS = 0.25


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def read_json(path):
    require(path.is_file() and not path.is_symlink() and
            0 < path.stat().st_size <= MAX_JSON_BYTES, 'invalid JSON source')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'duplicate JSON key')
            result[key] = value
        return result
    return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def valid_sha(value):
    return type(value) is str and SHA.fullmatch(value) is not None


def valid_pts(value):
    return type(value) in (int, float) and 0 <= value <= 14400 and value == value and value != float('inf')


def build(directory, worksheet_path):
    require(directory.is_dir() and not directory.is_symlink(), 'invalid frame directory')
    manifest_path = directory / 'manifest.json'
    manifest = read_json(manifest_path)
    worksheet = read_json(worksheet_path)
    require(type(manifest) is dict and manifest.get('schema_version') == 1 and
            manifest.get('status') == 'offline_multiframe_roi_geometry_unverified' and
            manifest.get('ocr_confirmed') is False and
            manifest.get('eligible_for_equity') == 0 and
            manifest.get('manual_review_required') is True and
            type(manifest.get('frames')) is list and
            1 <= len(manifest['frames']) <= MAX_FRAMES,
            'invalid unverified frame manifest')
    require(type(worksheet) is dict and worksheet.get('schema_version') == 1 and
            worksheet.get('status') == 'ocr_review_worksheet_not_confirmed' and
            worksheet.get('card_claims_verified') is False and
            worksheet.get('equity_or_ev_calculated') is False and
            type(worksheet.get('hands')) is list and
            1 <= len(worksheet['hands']) <= 100,
            'invalid unverified OCR worksheet')
    require(valid_sha(manifest.get('source_plan_sha256')) and
            manifest['source_plan_sha256'] == worksheet.get('source_plan_sha256') and
            valid_sha(manifest.get('source_video_sha256')) and
            manifest['source_video_sha256'] == worksheet.get('source_video_sha256_claim') and
            valid_sha(worksheet.get('source_proposals_sha256')),
            'worksheet/frames provenance mismatch')
    frames = []
    used = set()
    total = 0
    for row in manifest['frames']:
        require(type(row) is dict and
                {'hand_id', 'table_id', 'pts_seconds', 'frame', 'frame_sha256'} <= set(row) and
                type(row['hand_id']) is str and type(row['table_id']) is str and
                valid_pts(row['pts_seconds']) and type(row['frame']) is str and
                FRAME.fullmatch(row['frame']) is not None and
                valid_sha(row['frame_sha256']) and row['frame'] not in used,
                'invalid frame entry')
        used.add(row['frame'])
        path = directory / row['frame']
        require(path.is_file() and not path.is_symlink() and
                0 < path.stat().st_size <= 16 * 1024 * 1024 and
                sha256(path) == row['frame_sha256'], 'missing or altered frame')
        total += path.stat().st_size
        require(total <= MAX_IMAGE_BYTES, 'frame images exceed size limit')
        with Image.open(path) as img:
            require(img.format == 'PNG' and 64 <= img.width <= 8192 and
                    64 <= img.height <= 8192, 'invalid frame image')
            img.verify()
        frames.append({'hand_id': row['hand_id'], 'table_id': row['table_id'],
                       'pts_seconds': row['pts_seconds'], 'sha256': row['frame_sha256'],
                       'image': 'data:image/png;base64,' + base64.b64encode(path.read_bytes()).decode('ascii')})
    hands = []
    seen_hands = set()
    for hand in worksheet['hands']:
        require(type(hand) is dict and type(hand.get('hand_id')) is str and
                type(hand.get('table_id')) is str and hand['hand_id'] not in seen_hands and
                valid_pts(hand.get('start_seconds')) and valid_pts(hand.get('end_seconds')) and
                hand['start_seconds'] < hand['end_seconds'] and
                hand.get('human_review_required') is True and
                hand.get('machine_cards_confirmed') is False and
                hand.get('eligible_for_equity') is False and
                type(hand.get('observations')) is list,
                'invalid OCR hand')
        seen_hands.add(hand['hand_id'])
        observations = []
        for obs in hand['observations']:
            require(type(obs) is dict and obs.get('hand_id') == hand['hand_id'] and
                    obs.get('table_id') == hand['table_id'] and
                    obs.get('field') in ('hero_card', 'board_card', 'action', 'pot', 'stack', 'variant') and
                    type(obs.get('value')) is str and 1 <= len(obs['value']) <= 80 and
                    valid_pts(obs.get('pts_seconds')) and
                    hand['start_seconds'] <= obs['pts_seconds'] <= hand['end_seconds'] and
                    type(obs.get('confidence')) in (int, float) and
                    0 <= obs['confidence'] <= 1 and
                    (type(obs.get('slot')) is int and 0 <= obs['slot'] <
                     (6 if obs['field'] == 'hero_card' else 5)
                     if obs['field'] in ('hero_card', 'board_card') else obs.get('slot') is None),
                    'invalid OCR observation')
            matches = [(abs(frame['pts_seconds'] - obs['pts_seconds']), idx)
                       for idx, frame in enumerate(frames)
                       if frame['hand_id'] == hand['hand_id'] and
                       frame['table_id'] == hand['table_id']]
            distance, index = min(matches) if matches else (None, None)
            exact = distance is not None and distance <= MATCH_TOLERANCE_SECONDS
            observations.append({'field': obs['field'], 'slot': obs['slot'],
                                 'suggested': obs['value'], 'confidence_raw': obs['confidence'],
                                 'pts_seconds': obs['pts_seconds'],
                                 'frame_index': index, 'frame_delta_seconds': distance,
                                 'can_accept_after_human_review': exact})
        hands.append({'hand_id': hand['hand_id'], 'table_id': hand['table_id'],
                      'observations': observations})
    require(all(frame['hand_id'] in seen_hands and any(
            hand['hand_id'] == frame['hand_id'] and hand['table_id'] == frame['table_id']
            for hand in hands) for frame in frames), 'unbound frame hand/table')
    return {'schema_version': 1, 'status': 'offline_ocr_human_review_ui_unconfirmed',
            'source_video_sha256': manifest['source_video_sha256'],
            'source_plan_sha256': manifest['source_plan_sha256'],
            'source_worksheet_sha256': sha256(worksheet_path),
            'source_frame_manifest_sha256': sha256(manifest_path),
            'frames': frames, 'hands': hands, 'eligible_for_equity': 0,
            'equity_or_ev_calculated': False, 'human_review_required': True}


PAGE = r'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'none'; base-uri 'none'; form-action 'none'">
<title>PLO Trainee — revisão de evidências OCR</title>
<style>body{font:15px system-ui;background:#111827;color:#e5e7eb;max-width:1080px;margin:25px auto;padding:16px}h1{font-size:22px}section{background:#1f2937;border:1px solid #374151;border-radius:12px;margin:18px 0;padding:16px}.row{display:grid;grid-template-columns:1fr 1fr;gap:15px;padding:12px 0;border-top:1px solid #374151}img{max-width:100%;border:1px solid #4b5563;border-radius:8px}label{display:block;margin:8px 0}select,input,button{font:inherit;background:#111827;color:#fff;border:1px solid #6b7280;padding:8px;border-radius:6px}button{background:#0f766e;cursor:pointer;padding:12px}.warn{color:#fbbf24}.muted{color:#9ca3af}input{width:90%;box-sizing:border-box}@media(max-width:720px){.row{grid-template-columns:1fr}}</style></head><body>
<h1>PLO Trainee · revisão humana de OCR</h1><p class="warn">Sugestões não verificadas. Confiança OCR bruta não é probabilidade de acerto. Revise o quadro original antes de aceitar. Nenhuma decisão aqui habilita equity ou EV.</p>
<div id="content"></div><button id="export">Baixar rascunho de revisão (JSON)</button><p id="status" role="status" class="muted"></p>
<script>'use strict';
const data=__PAYLOAD__, content=document.getElementById('content');
const decisions=[];
function node(tag,text,parent){const el=document.createElement(tag);if(text!==null)el.textContent=text;parent.appendChild(el);return el;}
for(const hand of data.hands){const section=node('section',null,content);node('h2',hand.hand_id+' · '+hand.table_id,section);
 if(!hand.observations.length)node('p','Sem observações OCR nesta mão.',section);
 hand.observations.forEach((obs,i)=>{const row=node('div',null,section);row.className='row';const left=node('div',null,row),right=node('div',null,row);
 node('p',obs.field+(obs.slot===null?'':':'+obs.slot)+' · '+obs.pts_seconds+'s · OCR: '+obs.suggested+' · confiança bruta: '+obs.confidence_raw,left);
 if(obs.frame_index===null)node('p','Sem quadro da mesma mão/mesa.',left).className='warn';else{const frame=data.frames[obs.frame_index];const img=node('img',null,left);img.src=frame.image;img.alt='Quadro em '+frame.pts_seconds+' segundos';node('p','Quadro '+frame.pts_seconds+'s · diferença '+obs.frame_delta_seconds.toFixed(3)+'s',left).className=obs.can_accept_after_human_review?'muted':'warn';}
 const label=node('label','Decisão humana',right);const choice=node('select',null,label);
 for(const [value,name] of [['unknown','Não verificado'],['rejected','Rejeitar sugestão'],['accepted','Aceitar após verificar quadro']]){if(value==='accepted'&&!obs.can_accept_after_human_review)continue;const option=node('option',name,choice);option.value=value;}
 const valueLabel=node('label','Valor corrigido (opcional; não confirmado)',right),corrected=node('input',null,valueLabel);corrected.maxLength=80;corrected.placeholder='Deixe vazio se não corrigir';
 decisions.push({hand_id:hand.hand_id,table_id:hand.table_id,field:obs.field,slot:obs.slot,pts_seconds:obs.pts_seconds,frame_index:obs.frame_index,choice,corrected});
 });}
document.getElementById('export').onclick=()=>{const rows=decisions.map(d=>({hand_id:d.hand_id,table_id:d.table_id,field:d.field,slot:d.slot,pts_seconds:d.pts_seconds,decision:d.choice.value,corrected_value:d.corrected.value.trim().slice(0,80)||null,frame_sha256:d.frame_index===null?null:data.frames[d.frame_index].sha256}));
 const draft={schema_version:1,status:'human_review_draft_not_confirmed_for_math',source_plan_sha256:data.source_plan_sha256,source_worksheet_sha256:data.source_worksheet_sha256,source_frame_manifest_sha256:data.source_frame_manifest_sha256,decisions:rows,eligible_for_equity:0,equity_or_ev_calculated:false};
 const url=URL.createObjectURL(new Blob([JSON.stringify(draft,null,2)+'\n'],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='plo_ocr_review_draft.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);document.getElementById('status').textContent='Rascunho local exportado. Ainda não é anotação confirmada para cálculo.';};
</script></body></html>'''


def render(packet):
    payload = json.dumps(packet, ensure_ascii=True, allow_nan=False).replace('<', '\\u003c')
    return PAGE.replace('__PAYLOAD__', payload)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('frame_directory')
    parser.add_argument('worksheet_json')
    parser.add_argument('new_page_html')
    args = parser.parse_args(argv)
    directory, worksheet, output = Path(args.frame_directory), Path(args.worksheet_json), Path(args.new_page_html)
    require(output.suffix.lower() == '.html' and output.parent.is_dir() and
            not output.parent.is_symlink() and not output.exists() and
            not output.is_symlink() and output.resolve() not in
            {worksheet.resolve(), (directory/'manifest.json').resolve()},
            'output must be a distinct new HTML file')
    packet = build(directory, worksheet)
    source_hashes = (sha256(worksheet), sha256(directory/'manifest.json'))
    page = render(packet)
    require(source_hashes == (sha256(worksheet), sha256(directory/'manifest.json')),
            'source changed while generating review')
    with output.open('x', encoding='utf-8') as stream:
        stream.write(page)
    print(json.dumps({'page': str(output), 'hands': len(packet['hands']),
                      'frames': len(packet['frames']), 'eligible_for_equity': 0}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
