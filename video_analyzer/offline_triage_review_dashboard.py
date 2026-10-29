"""Offline read-only triage dashboard, bound to reviewed OCR ROI evidence.

Usage: python offline_triage_review_dashboard.py TIMELINE_JSON TRIAGE_JSON VIEWER_DIR NEW_OUTPUT_DIR
VIEWER_DIR must contain action_roi_report.json and assets/roi_NNN.png generated
by offline_action_evidence_viewer.py (or the verified evidence bundle).
Optional local video selection happens in the browser only. No upload, network,
clip export, player attribution, equity, EV, or automatic decision approval.
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
from offline_action_review_triage import build as rebuild_triage

SHA = re.compile(r'[a-f0-9]{64}\Z')
IDENT = re.compile(r'[A-Za-z0-9_-]{1,64}\Z')
ROI = re.compile(r'assets/roi_(\d{3})\.png\Z')
MAX_JSON = 8 * 1024 * 1024
MAX_CANDIDATES = 64
MAX_IMAGE_BYTES = 12 * 1024 * 1024


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate JSON key')
        result[key] = value
    return result


def load(path):
    p = Path(path)
    require(p.is_file() and not p.is_symlink() and 0 < p.stat().st_size <= MAX_JSON,
            'unsafe or oversized JSON')
    return json.loads(p.read_text('utf-8'), object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def safe_time(t):
    return type(t) in (int, float) and math.isfinite(t) and 0 <= t <= 86400


def assemble(timeline, triage, viewer):
    """Validate complete cross-document identity; return presentation-only rows."""
    require(type(timeline) is dict and type(triage) is dict and type(viewer) is dict,
            'invalid documents')
    require(triage.get('analysis_status') == 'offline_human_review_triage_only'
            and triage.get('ranking') == 'heuristic_not_equity_or_ev'
            and triage.get('hands_reconstructed') is False
            and triage.get('ready_for_equity_or_ev') is False
            and triage.get('clip_export_authorized') is False
            and type(triage.get('candidates')) is list
            and triage.get('total_candidates') == len(triage['candidates'])
            and len(triage['candidates']) <= MAX_CANDIDATES,
            'invalid triage or too many candidates')
    expected = rebuild_triage(timeline)
    # The source hash is verified by build() after loading the source file.
    require(all(triage.get(k) == v for k, v in expected.items()),
            'triage differs from deterministic source timeline')
    require(viewer.get('schema_version') == 1
            and viewer.get('analysis_status') == 'offline_read_only_action_roi_viewer'
            and viewer.get('hands_reconstructed') is False
            and viewer.get('ready_for_equity_or_ev') is False
            and type(viewer.get('hands')) is list,
            'invalid viewer provenance')
    lookup, hand_ids = {}, set()
    timeline_hands = {h['hand_id']: h for h in timeline['hands']}
    require(len(timeline_hands) == len(timeline['hands'])
            and len(viewer['hands']) == len(timeline_hands), 'viewer hand count mismatch')
    for hand in viewer['hands']:
        require(type(hand) is dict and type(hand.get('hand_id')) is str
                and IDENT.fullmatch(hand['hand_id']) and hand['hand_id'] not in hand_ids
                and type(hand.get('table_id')) is int and 1 <= hand['table_id'] <= 4
                and hand.get('variant') in ('PLO5', 'PLO6')
                and hand.get('ready_for_equity_or_ev') is False
                and type(hand.get('events')) is list,
                'invalid viewer hand')
        hand_ids.add(hand['hand_id'])
        require(hand['hand_id'] in timeline_hands, 'unknown viewer hand')
        source_hand = timeline_hands[hand['hand_id']]
        require(all(hand.get(k) == source_hand.get(k) for k in
                    ('table_id', 'variant', 'start_seconds', 'end_seconds')),
                'viewer hand bounds mismatch')
        source_events = {e['proposal_index']: e for e in source_hand['events']}
        require(len(source_events) == len(source_hand['events'])
                and len(hand['events']) == len(source_events),
                'viewer event count mismatch')
        for e in hand['events']:
            require(type(e) is dict and type(e.get('proposal_index')) is int
                    and e['proposal_index'] >= 0 and safe_time(e.get('timestamp_seconds'))
                    and type(e.get('field')) is str and type(e.get('value')) is str
                    and e.get('review') in ('confirmed', 'corrected')
                    and type(e.get('roi_png')) is str and ROI.fullmatch(e['roi_png'])
                    and int(ROI.fullmatch(e['roi_png']).group(1)) == e['proposal_index']
                    and type(e.get('roi_png_sha256')) is str
                    and SHA.fullmatch(e['roi_png_sha256']), 'invalid viewer event')
            require(e['proposal_index'] in source_events
                    and all(e.get(k) == source_events[e['proposal_index']].get(k)
                            for k in ('timestamp_seconds', 'field', 'value', 'review')),
                    'viewer event not in source timeline')
            key = (hand['hand_id'], e['proposal_index'])
            require(key not in lookup, 'duplicate viewer event')
            lookup[key] = (hand, e)
    rows = []
    for c in triage['candidates']:
        require(type(c) is dict and type(c.get('hand_id')) is str
                and type(c.get('proposal_index')) is int, 'invalid candidate')
        key = (c['hand_id'], c['proposal_index'])
        require(key in lookup, 'triage action missing from evidence viewer')
        hand, e = lookup[key]
        require(hand['table_id'] == c['table_id'] and hand['variant'] == c['variant']
                and e['field'] == 'action' and e['value'] == c['action_ocr']
                and e['timestamp_seconds'] == c['timestamp_seconds']
                and safe_time(c['preview_start_seconds'])
                and safe_time(c['preview_end_seconds'])
                and c['preview_start_seconds'] < c['preview_end_seconds']
                and hand['start_seconds'] <= c['preview_start_seconds']
                and c['preview_end_seconds'] <= hand['end_seconds'],
                'triage and evidence disagree')
        related = []
        for idx in c['nearby_bet_ocr_indices'] + c['nearby_pot_ocr_indices']:
            other = lookup.get((c['hand_id'], idx))
            if other:
                _, obs = other
                require(obs['field'] in ('bet', 'pot'), 'invalid nearby evidence field')
                related.append(f"{obs['field']}: {obs['value']} (OCR, PTS {obs['timestamp_seconds']}s)")
        rows.append({'hand_id': c['hand_id'], 'table_id': c['table_id'],
                     'variant': c['variant'], 'timestamp_seconds': c['timestamp_seconds'],
                     'action_ocr': c['action_ocr'], 'priority': c['review_priority_points'],
                     'preview_start_seconds': c['preview_start_seconds'],
                     'preview_end_seconds': c['preview_end_seconds'],
                     'proposal_index': c['proposal_index'], 'roi_png': e['roi_png'],
                     'roi_png_sha256': e['roi_png_sha256'],
                     'raw_ocr_text': e.get('raw_ocr_text', ''),
                     'review': e['review'], 'nearby': related,
                     'warnings': c['warnings'], 'unresolved_ocr_count': c['unresolved_ocr_count']})
    return rows


def page(rows):
    def esc(v):
        return html.escape(str(v), quote=True)
    blocks = []
    for n, r in enumerate(rows, 1):
        related = '; '.join(r['nearby']) or 'Nenhuma observação próxima disponível'
        warnings = '; '.join(r['warnings']) or 'Sem alertas registrados'
        blocks.append(
            '<article><div><h2>' + esc(f"{n}. Mesa {r['table_id']} · {r['variant']} · {r['hand_id']}") +
            '</h2><p>' + esc(f"Ação OCR: {r['action_ocr']} · PTS {r['timestamp_seconds']}s · prioridade heurística {r['priority']}") +
            '</p><p>' + esc(f"OCR bruto: {r['raw_ocr_text']} · revisão: {r['review']}") +
            '</p><p>' + esc(related) + '</p><p>' + esc(f"Alertas: {warnings} · OCR não resolvido: {r['unresolved_ocr_count']}") +
            '</p><button type="button" data-seek="' + esc(r['preview_start_seconds']) +
            '">Ir para ' + esc(r['preview_start_seconds']) + 's no vídeo local</button>' +
            '<p><small>Janela sugerida: ' + esc(r['preview_start_seconds']) + '–' +
            esc(r['preview_end_seconds']) + 's. Não autoriza exportação de clipe.</small></p></div>' +
            '<img src="' + esc(r['roi_png']) + '" alt="Evidência OCR ' + esc(r['proposal_index']) + '"></article>')
    return '''<!doctype html><html lang="pt-BR"><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src 'self'; media-src blob:; script-src 'unsafe-inline'; style-src 'unsafe-inline'; object-src 'none'; base-uri 'none'; form-action 'none'">
<title>PLO Trainee · triagem de revisão offline</title>
<style>body{font:15px system-ui;background:#101827;color:#e5e7eb;margin:0}main{max-width:1050px;margin:auto;padding:20px}article{display:flex;justify-content:space-between;gap:20px;flex-wrap:wrap;padding:16px;border:1px solid #475569;border-radius:12px;margin:16px 0;background:#1f2937}article div{flex:1;min-width:260px}article img{max-width:300px;max-height:180px;object-fit:contain}button{padding:10px;cursor:pointer}video{max-width:100%;max-height:300px}p{line-height:1.45}.warn{color:#fcd34d}</style>
<main><h1>PLO Trainee · fila de revisão de ações OCR</h1>
<p class="warn">Somente gravações offline. Prioridade não é EV ou qualidade da jogada. Jogador, regras da aposta, equity e EV não verificados.</p>
<label>Selecionar vídeo local (não enviado): <input id="localvideo" type="file" accept="video/mp4,video/webm"></label>
<p id="notice" role="status">Nenhum vídeo selecionado.</p><video id="preview" controls preload="metadata"></video>
<div id="queue">__CARDS__</div></main>
<script>
(()=>{'use strict';const input=document.getElementById('localvideo');const player=document.getElementById('preview');const notice=document.getElementById('notice');let url=null;
input.addEventListener('change',()=>{if(url){URL.revokeObjectURL(url);url=null;}player.removeAttribute('src');player.load();const f=input.files&&input.files[0];if(!f){notice.textContent='Nenhum vídeo selecionado.';return;}if(!['video/mp4','video/webm'].includes(f.type)){notice.textContent='Formato não aceito.';return;}url=URL.createObjectURL(f);player.src=url;notice.textContent='Vídeo local selecionado. Confirme visualmente a gravação e a mesa.';});
document.getElementById('queue').addEventListener('click',e=>{const b=e.target.closest('button[data-seek]');if(!b)return;if(!url){notice.textContent='Selecione primeiro o vídeo original local.';return;}const t=Number(b.dataset.seek);if(Number.isFinite(t)&&t>=0){player.currentTime=t;notice.textContent='Navegação solicitada para '+t+'s. Confira a mesa correta no vídeo.';}});
})();</script></html>'''.replace('__CARDS__', '\n'.join(blocks))


def build(timeline_path, triage_path, viewer_dir, output_dir):
    timeline_path, triage_path, viewer_dir, output_dir = map(
        Path, (timeline_path, triage_path, viewer_dir, output_dir))
    require(viewer_dir.is_dir() and not viewer_dir.is_symlink(), 'unsafe viewer directory')
    report_path = viewer_dir / 'action_roi_report.json'
    require(output_dir.parent.is_dir() and not output_dir.parent.is_symlink()
            and not output_dir.exists() and not output_dir.is_symlink()
            and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,100}', output_dir.name),
            'output must be a new safe directory')
    require(all(not output_dir.resolve().is_relative_to(p.resolve()) for p in
                (timeline_path, triage_path, viewer_dir)), 'output inside evidence')
    timeline, triage, viewer = (load(p) for p in (timeline_path, triage_path, report_path))
    source_hashes = [digest(p) for p in (timeline_path, triage_path, report_path)]
    require(triage.get('source_timeline_sha256') == source_hashes[0]
            and viewer.get('source_action_timeline_sha256') == source_hashes[0],
            'timeline hash mismatch')
    rows = assemble(timeline, triage, viewer)
    assets = {}
    for r in rows:
        rel = r['roi_png']
        p = viewer_dir / rel
        require(p.is_file() and not p.is_symlink()
                and 8 <= p.stat().st_size <= MAX_IMAGE_BYTES
                and digest(p) == r['roi_png_sha256'], 'missing or modified ROI')
        with p.open('rb') as f:
            require(f.read(8) == b'\x89PNG\r\n\x1a\n', 'invalid PNG')
        require(rel not in assets or assets[rel][1] == r['roi_png_sha256'], 'conflicting ROI')
        assets[rel] = (p, r['roi_png_sha256'])
    with tempfile.TemporaryDirectory(prefix='.plo_triage_dashboard_', dir=output_dir.parent) as temp:
        stage = Path(temp) / 'dashboard'
        (stage / 'assets').mkdir(parents=True)
        for rel, (source, expected_sha) in sorted(assets.items()):
            target = stage / rel
            shutil.copyfile(source, target)
            require(digest(target) == expected_sha, 'ROI copy mismatch')
        (stage / 'index.html').write_text(page(rows), 'utf-8')
        manifest = {'schema_version': 1,
                    'analysis_status': 'offline_read_only_triage_dashboard_only',
                    'source_timeline_sha256': source_hashes[0],
                    'source_triage_sha256': source_hashes[1],
                    'source_viewer_report_sha256': source_hashes[2],
                    'dashboard_html_sha256': digest(stage / 'index.html'),
                    'assets_sha256': {k: v[1] for k, v in sorted(assets.items())},
                    'candidate_count': len(rows), 'ready_for_equity_or_ev': False,
                    'clip_export_authorized': False,
                    'warning': 'Ranking is OCR review priority, not mathematical poker impact. Source video and OCR accuracy not independently verified here.'}
        (stage / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False,
                                                       indent=2, allow_nan=False) + '\n', 'utf-8')
        require([digest(p) for p in (timeline_path, triage_path, report_path)] == source_hashes
                and all(digest(p) == h for p, h in assets.values())
                and not output_dir.exists(), 'evidence changed during generation')
        os.rename(stage, output_dir)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('timeline_json', 'triage_json', 'viewer_dir', 'new_output_dir'):
        parser.add_argument(name)
    args = parser.parse_args(argv)
    print(json.dumps(build(args.timeline_json, args.triage_json,
                           args.viewer_dir, args.new_output_dir), allow_nan=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
