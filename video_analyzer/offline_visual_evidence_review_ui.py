"""Offline reviewer UI for linked OCR evidence. Exports an UNTRUSTED draft only.

Usage: python offline_visual_evidence_review_ui.py OCR.json RECON.json REVIEW.json FRAMES_DIR NEW.html
Requires the audited provenance chain; never calculates equity or EV.
"""
import argparse
import base64
import html
import json
from pathlib import Path

import offline_hand_frame_evidence_audit as audit
import offline_hand_street_review as review


def build(ocr_path, reconstruction_path, reviewed_path, frames_dir):
    result = audit.build(ocr_path, reconstruction_path, reviewed_path, frames_dir)
    manifest = review.read(Path(frames_dir) / 'manifest.json')
    frames = {}
    for row in manifest['frames']:
        file = Path(frames_dir) / row['frame']
        # audit.build already checked file bytes, PNG format, SHA and symlink safety.
        frames[(row['hand_id'], row['table_id'], row['frame_sha256'])] = (
            'data:image/png;base64,' + base64.b64encode(file.read_bytes()).decode('ascii'))
    require = audit.require
    cards = []
    for hand in result['hands']:
        for claim in hand['claims']:
            evidence = []
            for obs in claim['matching_frame_observations']:
                key = (hand['hand_id'], hand['table_id'], obs['frame_sha256'])
                require(key in frames, 'missing audited frame')
                evidence.append({'sha256': obs['frame_sha256'], 'pts': obs['pts_seconds'],
                                 'observation_index': obs['observation_index'], 'image': frames[key]})
            cards.append({'hand_id': hand['hand_id'], 'table_id': hand['table_id'],
                          'field': claim['field'], 'slot': claim['slot'],
                          'value_unverified': claim['reviewer_value_unverified'],
                          'evidence': evidence})
    return {'schema_version': 1, 'status': 'offline_visual_review_draft_only',
            'source_review_sha256': review.digest(Path(reviewed_path)),
            'source_frame_manifest_sha256': result['source_frame_manifest_sha256'],
            'source_video_sha256_claim': result['source_video_sha256_claim'],
            'cards': cards, 'eligible_for_equity': 0, 'equity_or_ev_calculated': False}


def render(packet):
    # Encode untrusted text as JSON, escaping HTML/script-breaking characters.
    data = json.dumps(packet, ensure_ascii=True, allow_nan=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    return '''<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'none'">
<title>PLO Trainee - Revisão visual</title>
<style>body{font:16px system-ui;background:#101827;color:#e9eef8;max-width:1000px;margin:auto;padding:24px}
article{border:1px solid #40546b;border-radius:12px;padding:16px;margin:16px 0}img{max-width:100%;border-radius:6px}
figure{margin:8px 0}figcaption{font-size:12px;overflow-wrap:anywhere}select,button,textarea{padding:9px;font:inherit}
textarea{display:block;width:95%;height:48px;margin:10px 0}button{cursor:pointer}</style>
<h1>Revisão visual de evidências — PLO5/PLO6</h1>
<p>As cartas e ações são declarações não autenticadas. A revisão humana não comprova a verdade do vídeo e não libera equity/EV.</p>
<main id="cards"></main><button id="export">Exportar rascunho JSON</button>
<script>const DATA=''' + data + ''';
const root=document.getElementById('cards'),inputs=[];
for(const c of DATA.cards){
 const article=document.createElement('article');
 const heading=document.createElement('h2');heading.textContent=c.table_id+' / '+c.hand_id+' — '+c.field+' '+(c.slot??'');article.append(heading);
 const value=document.createElement('p');value.textContent='Valor sugerido (não verificado): '+c.value_unverified;article.append(value);
 for(const e of c.evidence){const f=document.createElement('figure'),img=document.createElement('img'),cap=document.createElement('figcaption');
 img.src=e.image;img.alt='Quadro extraído';cap.textContent='t='+e.pts+'s | SHA-256 '+e.sha256;f.append(img,cap);article.append(f);}
 if(!c.evidence.length){const p=document.createElement('p');p.textContent='Sem quadro associado: confirmação visual indisponível.';article.append(p);}
 const select=document.createElement('select');
 for(const [v,t] of [['uncertain','Incerto / não revisado'],['not_visible','Não visível'],...(c.evidence.length?[['seen_by_reviewer','Visível segundo revisor']]:[])]){
 const o=document.createElement('option');o.value=v;o.textContent=t;select.append(o);}article.append(select);
 const note=document.createElement('textarea');note.maxLength=500;note.placeholder='Observação opcional';article.append(note);
 root.append(article);inputs.push({select,note});}
document.getElementById('export').addEventListener('click',()=>{
 const draft={schema_version:1,status:'offline_visual_review_untrusted_draft',source_review_sha256:DATA.source_review_sha256,
 source_frame_manifest_sha256:DATA.source_frame_manifest_sha256,source_video_sha256_claim:DATA.source_video_sha256_claim,
 reviewer_claims_not_authenticated:true,math_ready:false,eligible_for_equity:0,equity_or_ev_calculated:false,
 claims:DATA.cards.map((c,i)=>({hand_id:c.hand_id,table_id:c.table_id,field:c.field,slot:c.slot,
 value_unverified:c.value_unverified,visual_review_status:inputs[i].select.value,reviewer_note:inputs[i].note.value,
 evidence:c.evidence.map(e=>({frame_sha256:e.sha256,pts_seconds:e.pts,observation_index:e.observation_index}))}))};
 const url=URL.createObjectURL(new Blob([JSON.stringify(draft,null,2)+'\\n'],{type:'application/json'}));
 const a=document.createElement('a');a.href=url;a.download='visual_review_draft.json';a.click();URL.revokeObjectURL(url);});
</script></html>'''


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('ocr', 'reconstruction', 'reviewed', 'frames_dir', 'new_html'):
        p.add_argument(name)
    args = p.parse_args(argv)
    target = Path(args.new_html)
    audit.require(target.suffix == '.html' and target.parent.is_dir() and
                  not target.parent.is_symlink() and not target.exists() and not target.is_symlink(),
                  'output must be a new HTML file')
    page = render(build(args.ocr, args.reconstruction, args.reviewed, args.frames_dir))
    with target.open('x', encoding='utf-8') as out:
        out.write(page)
    print(json.dumps({'output': str(target), 'eligible_for_equity': 0}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
