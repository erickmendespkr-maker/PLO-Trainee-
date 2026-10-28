"""Build a local, read-only OCR-image viewer for reviewed PLO5/PLO6 action timelines.

python offline_action_evidence_viewer.py OCR_DIR REVIEWED_JSON HAND_DRAFTS_JSON ACTION_TIMELINE_JSON NEW_OUTPUT_DIR

Only hash-bound, manually reviewed OCR observations are displayed. No inference of
players, betting legality, equity or EV. All images are copied from verified ROI PNGs.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import os
from pathlib import Path
import re
import shutil
import tempfile

SHA = re.compile(r'[0-9a-f]{64}\Z')
PNG = re.compile(r'roi_\d{3}\.png\Z')
MAX_JSON = 8 * 1024 * 1024
MAX_PNG = 12 * 1024 * 1024
MAX_ASSETS = 64
MAX_ASSET_BYTES = 48 * 1024 * 1024


def need(ok, reason):
    if not ok:
        raise ValueError(reason)


def unique(pairs):
    out = {}
    for key, value in pairs:
        need(key not in out, 'duplicate JSON key')
        out[key] = value
    return out


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def load(path):
    path = Path(path)
    need(path.is_file() and not path.is_symlink() and 0 < path.stat().st_size <= MAX_JSON,
         'unsafe or oversized JSON')
    return json.loads(path.read_text('utf-8'), object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def seconds(value):
    return type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 86400


def hexsha(value):
    return type(value) is str and SHA.fullmatch(value) is not None


def build(ocr_dir, reviewed_json, drafts_json, timeline_json, output_dir):
    ocr_dir, reviewed_json, drafts_json, timeline_json, output_dir = map(
        Path, (ocr_dir, reviewed_json, drafts_json, timeline_json, output_dir))
    need(ocr_dir.is_dir() and not ocr_dir.is_symlink(), 'unsafe OCR directory')
    need(output_dir.parent.is_dir() and not output_dir.parent.is_symlink()
         and not output_dir.exists() and not output_dir.is_symlink()
         and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,100}', output_dir.name),
         'output must be a new safe directory')
    for source in (ocr_dir, reviewed_json, drafts_json, timeline_json):
        need(not output_dir.resolve().is_relative_to(source.resolve()), 'output inside evidence')
    ocr_path = ocr_dir / 'roi_ocr_proposals.json'
    ocr, reviewed, drafts, timeline = (load(p) for p in
        (ocr_path, reviewed_json, drafts_json, timeline_json))
    need(type(ocr) is dict and ocr.get('schema_version') == 1
         and ocr.get('analysis_status') == 'offline_refined_roi_ocr_proposals_only'
         and ocr.get('ready_for_equity_or_ev') is False
         and ocr.get('hands_reconstructed') is False
         and type(ocr.get('proposals')) is list and 1 <= len(ocr['proposals']) <= MAX_ASSETS,
         'invalid OCR report')
    need(type(reviewed) is dict
         and reviewed.get('analysis_status') == 'offline_human_reviewed_ocr_observations_only'
         and reviewed.get('source_roi_ocr_report_sha256') == sha(ocr_path)
         and reviewed.get('ready_for_equity_or_ev') is False
         and reviewed.get('hands_reconstructed') is False
         and type(reviewed.get('observations')) is list
         and len(reviewed['observations']) == len(ocr['proposals']), 'invalid reviewed report')
    need(type(drafts) is dict
         and drafts.get('analysis_status') == 'offline_reviewed_hand_drafts_only'
         and drafts.get('source_reviewed_report_sha256') == sha(reviewed_json)
         and drafts.get('source_roi_ocr_report_sha256') == sha(ocr_path)
         and drafts.get('ready_for_equity_or_ev') is False
         and drafts.get('hands_reconstructed') is False
         and type(drafts.get('hands')) is list and 1 <= len(drafts['hands']) <= 200,
         'invalid draft provenance')
    need(type(timeline) is dict and timeline.get('schema_version') == 1
         and timeline.get('analysis_status') == 'offline_action_bet_evidence_only'
         and timeline.get('source_hand_drafts_sha256') == sha(drafts_json)
         and timeline.get('source_reviewed_report_sha256') == sha(reviewed_json)
         and timeline.get('source_boundaries_sha256') == drafts.get('source_boundaries_sha256')
         and timeline.get('ready_for_equity_or_ev') is False
         and timeline.get('hands_reconstructed') is False
         and type(timeline.get('hands')) is list
         and len(timeline['hands']) == len(drafts['hands']), 'invalid action timeline provenance')
    assets = {}
    for index, (proposal, obs) in enumerate(zip(ocr['proposals'], reviewed['observations'])):
        need(type(proposal) is dict and type(obs) is dict
             and type(obs.get('proposal_index')) is int and obs['proposal_index'] == index
             and type(proposal.get('table_id')) is int and 1 <= proposal['table_id'] <= 4
             and obs.get('table_id') == proposal['table_id']
             and obs.get('field') == proposal.get('field')
             and obs.get('frame_file') == proposal.get('frame_file')
             and obs.get('source_frame_sha256') == proposal.get('source_frame_sha256')
             and seconds(proposal.get('decoded_source_pts_seconds'))
             and obs.get('decoded_source_pts_seconds') == proposal['decoded_source_pts_seconds']
             and proposal.get('roi_png') == f'roi_{index:03d}.png'
             and PNG.fullmatch(proposal['roi_png'])
             and hexsha(proposal.get('roi_png_sha256'))
             and obs.get('roi_png') == proposal['roi_png']
             and obs.get('roi_png_sha256') == proposal['roi_png_sha256']
             and obs.get('raw_ocr_text') == proposal.get('raw_ocr_text')
             and obs.get('decision') in ('confirmed', 'corrected', 'rejected', 'inconclusive', 'pending'),
             'invalid OCR/review evidence identity')
        if obs['decision'] in ('confirmed', 'corrected'):
            need(type(obs.get('normalized_value')) is str and bool(obs['normalized_value']),
                 'missing reviewed value')
        else:
            need(obs.get('normalized_value') is None, 'unresolved value promoted')
        path = ocr_dir / proposal['roi_png']
        need(path.is_file() and not path.is_symlink()
             and 8 <= path.stat().st_size <= MAX_PNG
             and sha(path) == proposal['roi_png_sha256'], 'missing or altered ROI PNG')
        with path.open('rb') as stream:
            need(stream.read(8) == b'\x89PNG\r\n\x1a\n', 'invalid ROI PNG signature')
        assets[index] = (path, proposal['roi_png_sha256'])
    drafts_by_id = {h.get('hand_id'): h for h in drafts['hands'] if type(h) is dict}
    need(len(drafts_by_id) == len(drafts['hands']), 'duplicate draft hands')
    seen_hands, seen_events, result_hands, needed_images = set(), set(), [], set()
    for hand in timeline['hands']:
        need(type(hand) is dict and type(hand.get('hand_id')) is str
             and hand['hand_id'] in drafts_by_id and hand['hand_id'] not in seen_hands
             and hand.get('ready_for_equity_or_ev') is False
             and hand.get('actor_and_betting_sequence_verified') is False
             and type(hand.get('events')) is list, 'invalid action hand')
        seen_hands.add(hand['hand_id'])
        draft = drafts_by_id[hand['hand_id']]
        need(all(hand.get(k) == draft.get(k) for k in
                 ('table_id', 'variant', 'start_seconds', 'end_seconds'))
             and type(hand['table_id']) is int and 1 <= hand['table_id'] <= 4
             and hand['variant'] in ('PLO5', 'PLO6')
             and seconds(hand['start_seconds']) and seconds(hand['end_seconds'])
             and hand['start_seconds'] < hand['end_seconds'], 'invalid hand bounds')
        expected = {}
        for field, entries in draft.get('reviewed_fields', {}).items():
            need(type(entries) is list, 'invalid reviewed fields')
            for entry in entries:
                idx = entry.get('proposal_index')
                need(type(idx) is int and idx not in expected, 'duplicate draft proposal')
                expected[idx] = (field, entry)
        need(type(draft.get('observation_indices')) is list
             and type(draft.get('unresolved_indices')) is list
             and set(expected) | set(draft['unresolved_indices']) == set(draft['observation_indices'])
             and len(draft['observation_indices']) == len(set(draft['observation_indices'])),
             'draft observation mismatch')
        rows, used = [], set()
        for event in hand['events']:
            need(type(event) is dict and type(event.get('proposal_index')) is int
                 and event['proposal_index'] in expected
                 and event['proposal_index'] not in used
                 and event['proposal_index'] not in seen_events
                 and seconds(event.get('timestamp_seconds')),
                 'invalid action event')
            idx = event['proposal_index']
            used.add(idx); seen_events.add(idx)
            field, entry = expected[idx]
            obs = reviewed['observations'][idx]
            need(event.get('field') == field == obs['field']
                 and event.get('value') == entry.get('value') == obs.get('normalized_value')
                 and event.get('review') == entry.get('review') == obs.get('decision')
                 and event['review'] in ('confirmed', 'corrected')
                 and event['timestamp_seconds'] == entry.get('timestamp_seconds')
                 == obs['decoded_source_pts_seconds']
                 and obs['table_id'] == hand['table_id']
                 and hand['start_seconds'] <= event['timestamp_seconds'] < hand['end_seconds'],
                 'action event not bound to reviewed OCR')
            needed_images.add(idx)
            rows.append({'proposal_index': idx, 'timestamp_seconds': event['timestamp_seconds'],
                         'field': field, 'value': event['value'], 'review': event['review'],
                         'raw_ocr_text': obs['raw_ocr_text'], 'roi_png': f'assets/roi_{idx:03d}.png',
                         'roi_png_sha256': assets[idx][1],
                         'board_phase_evidence': event.get('board_phase_evidence', 'street_unknown')})
        need(used == set(expected), 'timeline missing or extra events')
        result_hands.append({'hand_id': hand['hand_id'], 'table_id': hand['table_id'],
                             'variant': hand['variant'], 'start_seconds': hand['start_seconds'],
                             'end_seconds': hand['end_seconds'], 'events': rows,
                             'warnings': hand.get('warnings', []),
                             'ready_for_equity_or_ev': False})
    need(len(needed_images) <= MAX_ASSETS and
         sum(assets[idx][0].stat().st_size for idx in needed_images) <= MAX_ASSET_BYTES,
         'too many evidence images')
    report = {'schema_version': 1, 'analysis_status': 'offline_read_only_action_roi_viewer',
              'source_action_timeline_sha256': sha(timeline_json),
              'source_hand_drafts_sha256': sha(drafts_json),
              'source_reviewed_report_sha256': sha(reviewed_json),
              'source_roi_ocr_report_sha256': sha(ocr_path),
              'hands_reconstructed': False, 'ready_for_equity_or_ev': False,
              'confidence': 'OCR engine scores are not calibrated correctness probabilities',
              'hands': result_hands}
    payload = json.dumps(report, ensure_ascii=False, allow_nan=False).replace('<', '\\u003c')
    viewer = '''<!doctype html><html lang="pt-BR"><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'">
<title>PLO Trainee — revisão de evidências offline</title>
<style>body{font:15px system-ui;background:#111827;color:#f1f5f9;margin:0}main{max-width:1000px;margin:auto;padding:22px}section{background:#1f2937;border:1px solid #475569;border-radius:10px;padding:14px;margin:16px 0}article{display:flex;gap:18px;border-top:1px solid #475569;padding:12px 0;align-items:center;flex-wrap:wrap}img{max-width:300px;max-height:170px;object-fit:contain;background:#0b1220}small{color:#cbd5e1}.warn{color:#fcd34d}</style>
<main><h1>PLO Trainee · evidências OCR por mão</h1><p class="warn">Revisão manual obrigatória. Sem reconstrução de apostas, equity ou EV.</p><div id="hands"></div></main>
<script>const DATA=__DATA__;const root=document.getElementById('hands');
function el(tag,txt,parent){const x=document.createElement(tag);if(txt!==null)x.textContent=String(txt);parent.appendChild(x);return x}
for(const hand of DATA.hands){const s=el('section',null,root);el('h2','Mesa '+hand.table_id+' · '+hand.hand_id+' · '+hand.variant,s);el('small',hand.start_seconds+'–'+hand.end_seconds+' segundos · limites manuais não verificados',s);for(const e of hand.events){const a=el('article',null,s);const img=el('img',null,a);img.src=e.roi_png;img.alt='ROI '+e.proposal_index;const d=el('div',null,a);el('strong',e.field+' · '+e.value,d);el('p','PTS '+e.timestamp_seconds+'s · '+e.review+' · '+e.board_phase_evidence,d);el('small','OCR bruto: '+e.raw_ocr_text,d);el('p','SHA-256 ROI: '+e.roi_png_sha256,d)}if(!hand.events.length)el('p','Nenhuma observação resolvida.',s)}}
</script></html>'''.replace('__DATA__', payload)
    with tempfile.TemporaryDirectory(prefix='.plo_action_roi_', dir=output_dir.parent) as temp:
        stage = Path(temp)
        (stage / 'assets').mkdir()
        for idx in sorted(needed_images):
            source, digest = assets[idx]
            target = stage / 'assets' / f'roi_{idx:03d}.png'
            shutil.copyfile(source, target)
            need(sha(target) == digest, 'copied ROI mismatch')
        (stage / 'action_roi_report.json').write_text(
            json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + '\n', 'utf-8')
        (stage / 'index.html').write_text(viewer, 'utf-8')
        need(sha(ocr_path) == report['source_roi_ocr_report_sha256']
             and sha(reviewed_json) == report['source_reviewed_report_sha256']
             and sha(drafts_json) == report['source_hand_drafts_sha256']
             and sha(timeline_json) == report['source_action_timeline_sha256'],
             'source changed during generation')
        for idx in needed_images:
            need(sha(assets[idx][0]) == assets[idx][1], 'ROI changed during generation')
        need(not output_dir.exists(), 'output appeared during generation')
        os.rename(stage, output_dir)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('ocr_dir', 'reviewed_json', 'hand_drafts_json', 'action_timeline_json', 'new_output_dir'):
        parser.add_argument(name)
    args = parser.parse_args(argv)
    result = build(args.ocr_dir, args.reviewed_json, args.hand_drafts_json,
                   args.action_timeline_json, args.new_output_dir)
    print(json.dumps({'hands': len(result['hands']), 'ready_for_equity_or_ev': False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
