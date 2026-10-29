"""Offline gallery for human acknowledgement of extracted card frames.

This verifies file hashes and human acknowledgement records, NOT card visibility,
OCR accuracy, actor identity, action quality or decoded-frame PTS.

CLI:
  python offline_audited_card_gallery.py generate SNAPSHOT_DIR REVIEW_JSON NEW_HTML
  python offline_audited_card_gallery.py verify SNAPSHOT_DIR REVIEW_JSON CONFIRMATION_JSON NEW_JSON
"""
from __future__ import annotations
import argparse
import math
import json
from pathlib import Path
import re

from offline_plo_equity_monte_carlo import read_json, require
from offline_reviewed_equity_clip_report import digest, safe_file

FRAME_NAME = re.compile(r'frame_[0-9]{2}\.png\Z')
SHA = re.compile(r'[a-f0-9]{64}\Z')


def load(snapshot_dir, review_path):
    root = Path(snapshot_dir)
    require(root.is_dir() and not root.is_symlink(), 'invalid snapshot directory')
    manifest_file = safe_file(root / 'manifest.json', max_bytes=2_000_000)
    review_file = safe_file(review_path, max_bytes=2_000_000)
    manifest, review = read_json(manifest_file), read_json(review_file)
    require(type(manifest) is dict and manifest.get('schema_version') == 1 and
            type(manifest.get('schema_version')) is int and
            manifest.get('analysis_status') == 'manual_timestamp_frame_extraction_only' and
            manifest.get('card_visibility_verified') is False and
            manifest.get('exact_decoded_frame_timestamp_verified') is False and
            manifest.get('ocr_semantics_verified') is False, 'unsupported audit manifest')
    require(manifest.get('source_manual_review_sha256') == digest(review_file),
            'manual review fingerprint mismatch')
    require(review.get('source_clip_sha256') == manifest.get('source_clip_sha256') and
            review.get('source_binding_sha256') == manifest.get('source_binding_sha256'),
            'review source mismatch')
    for key in ('hand_id', 'table_id', 'variant', 'proposal_index'):
        require(type(review.get(key)) is type(manifest.get(key)) and
                review[key] == manifest[key], 'hand identity mismatch')
    frames = manifest.get('frames')
    links = manifest.get('card_frame_links')
    require(type(frames) is list and 1 <= len(frames) <= 11 and
            type(links) is list and len(links) == len(review['hero_cards'] + review['board_cards']),
            'invalid frame or card count')
    names = {}
    stamps = {}
    for frame in frames:
        require(type(frame) is dict and set(frame) ==
                {'file', 'requested_clip_timestamp_seconds', 'sha256'}, 'invalid frame record')
        name, sha = frame['file'], frame['sha256']
        require(type(name) is str and FRAME_NAME.fullmatch(name) and name not in names and
                type(sha) is str and SHA.fullmatch(sha), 'unsafe frame name or digest')
        stamp = frame['requested_clip_timestamp_seconds']
        require(type(stamp) in (int, float) and math.isfinite(stamp) and stamp >= 0,
                'invalid frame timestamp')
        png = safe_file(root / name, max_bytes=50_000_000)
        require(digest(png) == sha, 'frame hash mismatch')
        names[name] = sha
        stamps[name] = float(stamp)
    cards = review['hero_cards'] + review['board_cards']
    require(len(cards) == len(set(cards)), 'duplicate reviewed cards')
    require([x.get('card') for x in links if type(x) is dict] ==
            [x.get('card') for x in review.get('card_frame_evidence', [])],
            'card order differs from manual review')
    evidence = review.get('card_frame_evidence', [])
    for link, declared in zip(links, evidence):
        require(type(link) is dict and set(link) ==
                {'card', 'requested_clip_timestamp_seconds', 'frame_file'} and
                link['frame_file'] in names and link['card'] in cards and
                type(link['requested_clip_timestamp_seconds']) in (int, float) and
                math.isfinite(link['requested_clip_timestamp_seconds']) and
                float(link['requested_clip_timestamp_seconds']) == stamps[link['frame_file']] and
                float(link['requested_clip_timestamp_seconds']) == float(declared['clip_timestamp_seconds']),
                'invalid card/frame association')
    require(len({x['card'] for x in links}) == len(cards) and
            {x['frame_file'] for x in links} == set(names), 'duplicate or orphan card/frame link')
    return manifest, review, names, digest(manifest_file), digest(review_file)


HTML = '''<!doctype html><html lang="pt-BR"><meta charset="utf-8"><title>PLO Trainee — quadros revisados</title>
<style>body{font:16px system-ui;background:#f4f6fa;color:#18243b;margin:24px}main{max-width:940px;margin:auto}
article{background:white;border:1px solid #ccd5e0;border-radius:10px;padding:14px;margin:12px 0}
img{width:100%;max-width:640px;height:auto;background:#18243b}label{display:block;margin:10px 0}
textarea{width:95%;min-height:72px}button{padding:10px 16px}.warning{background:#fff0ce;padding:14px}</style>
<main><h1>Revisão visual de quadros — PLO Trainee</h1>
<p class="warning">As cartas são declarações humanas. A integridade do PNG não comprova que a carta está visível.
Marque cada item somente após examinar a imagem. Isto NÃO valida OCR, jogador, PTS exato ou decisão estratégica.</p>
<div id="cards"></div><label>Notas sobre visibilidade, dúvidas e limitações<textarea id="notes"></textarea></label>
<button id="save">Exportar confirmação manual JSON</button><p id="status" role="status"></p></main>
<script id="context" type="application/json">__DATA__</script><script>
'use strict';const data=JSON.parse(document.getElementById('context').textContent);
const wrap=document.getElementById('cards');
for(const [i,c] of data.cards.entries()){
 const article=document.createElement('article'),title=document.createElement('h2');
 title.textContent=c.card+' — '+c.timestamp+' s';article.append(title);
 const img=document.createElement('img');img.src=c.frame;img.alt='Quadro extraído para '+c.card;article.append(img);
 const label=document.createElement('label'),check=document.createElement('input');
 check.type='checkbox';check.className='ack';check.dataset.index=String(i);
 label.append(check,document.createTextNode(' Examinei este quadro e confirmo manualmente a carta declarada.'));
 article.append(label);wrap.append(article);
}
document.getElementById('save').onclick=()=>{
 const checks=[...document.querySelectorAll('.ack')];
 const notes=document.getElementById('notes').value.trim();
 if(checks.some(x=>!x.checked)||notes.length<8||notes.length>2000){
 document.getElementById('status').textContent='Confirme todos os quadros e informe notas (8–2000 caracteres).';return;}
 const result={schema_version:1,source_manifest_sha256:data.manifest_sha,
 source_manual_review_sha256:data.review_sha,review_method:'human_snapshot_gallery_acknowledgement',
 card_acknowledgements:data.cards.map(c=>({card:c.card,frame_file:c.frame,frame_sha256:c.sha,
 human_confirmed:true})),review_notes:notes};
 const url=URL.createObjectURL(new Blob([JSON.stringify(result,null,2)+'\\n'],{type:'application/json'}));
 const a=document.createElement('a');a.href=url;a.download='snapshot_confirmation.json';a.click();
 setTimeout(()=>URL.revokeObjectURL(url),1000);
 document.getElementById('status').textContent='Confirmação manual exportada. Não é validação automática.';
};</script></html>'''


def render(manifest, review, names, manifest_sha, review_sha):
    cards = [{'card': x['card'], 'frame': x['frame_file'],
              'sha': names[x['frame_file']],
              'timestamp': x['requested_clip_timestamp_seconds']}
             for x in manifest['card_frame_links']]
    data = json.dumps({'manifest_sha': manifest_sha, 'review_sha': review_sha,
                       'cards': cards}, ensure_ascii=True).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    return HTML.replace('__DATA__', data)


def generate(snapshot_dir, review_path, html_path):
    manifest, review, names, mh, rh = load(snapshot_dir, review_path)
    out = Path(html_path)
    require(out.parent.resolve() == Path(snapshot_dir).resolve() and out.suffix == '.html' and
            not out.exists() and not out.is_symlink(), 'HTML must be new and inside snapshot directory')
    page = render(manifest, review, names, mh, rh)
    require(load(snapshot_dir, review_path)[3:] == (mh, rh), 'inputs changed')
    with out.open('x', encoding='utf-8') as f:
        f.write(page)
    return out


def verify(snapshot_dir, review_path, confirmation_path):
    manifest, review, names, mh, rh = load(snapshot_dir, review_path)
    path = safe_file(confirmation_path, max_bytes=2_000_000)
    original_sha = digest(path)
    data = read_json(path)
    require(type(data) is dict and set(data) == {'schema_version', 'source_manifest_sha256',
            'source_manual_review_sha256', 'review_method', 'card_acknowledgements',
            'review_notes'} and type(data['schema_version']) is int and data['schema_version'] == 1,
            'invalid confirmation schema')
    require(data['source_manifest_sha256'] == mh and data['source_manual_review_sha256'] == rh and
            data['review_method'] == 'human_snapshot_gallery_acknowledgement',
            'confirmation does not match reviewed source')
    notes = data['review_notes']
    require(type(notes) is str and 8 <= len(notes.strip()) <= 2000, 'human notes required')
    entries = data['card_acknowledgements']
    require(type(entries) is list and len(entries) == len(manifest['card_frame_links']),
            'all cards require acknowledgement')
    for link, entry in zip(manifest['card_frame_links'], entries):
        require(type(entry) is dict and set(entry) == {'card', 'frame_file', 'frame_sha256',
                'human_confirmed'} and entry['card'] == link['card'] and
                entry['frame_file'] == link['frame_file'] and
                entry['frame_sha256'] == names[link['frame_file']] and
                entry['human_confirmed'] is True, 'unconfirmed or altered card evidence')
    require(digest(path) == original_sha and load(snapshot_dir, review_path)[3:] == (mh, rh),
            'sources changed during verification')
    return {'schema_version': 1, 'analysis_status': 'human_snapshot_acknowledgement_recorded',
            'source_manifest_sha256': mh, 'source_manual_review_sha256': rh,
            'source_confirmation_sha256': original_sha, 'acknowledged_cards': len(entries),
            'human_confirmation_asserted': True, 'card_visibility_machine_verified': False,
            'ocr_semantics_verified': False, 'player_identity_verified': False,
            'strategic_correctness_verified': False, 'exact_decoded_pts_verified': False,
            'warning': 'Acknowledgements are human assertions; no machine vision validation.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('generate', 'verify'))
    parser.add_argument('snapshot_dir');parser.add_argument('review_json')
    parser.add_argument('third');parser.add_argument('fourth', nargs='?')
    args = parser.parse_args(argv)
    if args.operation == 'generate':
        require(args.fourth is None, 'unexpected argument')
        print(json.dumps({'html_created': str(generate(args.snapshot_dir, args.review_json, args.third))}))
    else:
        require(args.fourth is not None, 'output JSON required')
        out = Path(args.fourth)
        require(out.parent.is_dir() and not out.parent.is_symlink() and out.suffix == '.json' and
                not out.exists() and not out.is_symlink(), 'output must be new JSON')
        report = verify(args.snapshot_dir, args.review_json, args.third)
        with out.open('x', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False, allow_nan=False)
            f.write('\n')
        print(json.dumps({'acknowledged_cards': report['acknowledged_cards']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
