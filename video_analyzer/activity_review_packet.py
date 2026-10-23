"""Produce a self-contained, read-only OFFLINE decision review worksheet.

Input: activity_snapshot_chain's human-reviewed OCR decision *hints*.
Output: printable HTML and an intentionally UNCONFIRMED JSON review template.
No inferred poker actions, hidden cards, opponent ranges, equity, or EV.
The HTML never loads remote assets or embeds arbitrary local image paths.
"""
import argparse
import hashlib
from html import escape
import json
import math
from pathlib import Path, PurePosixPath
import re

_SHA = re.compile(r'[0-9a-f]{64}\Z')
_FIELDS = ('hero_cards', 'board', 'observed_action', 'pot_before_action', 'call_amount')


def _digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=False, allow_nan=False).encode('utf-8')).hexdigest()


def _number(value, label):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError(f'Invalid {label}')
    return value


def _safe_source(path):
    if not isinstance(path, str) or not path or '\\' in path or '\x00' in path:
        raise ValueError('Invalid image source')
    p = PurePosixPath(path)
    if p.is_absolute() or '..' in p.parts or path.startswith('./') or '://' in path:
        raise ValueError('Unsafe image source')
    return path


def build_review_packet(queue, *, expected_sha256=None):
    """Validate queue and return HTML plus blank, non-executable review JSON.

    Digest pins the *JSON queue*, not recording/frame authenticity. Caller must
    audit upstream image hashes separately before relying on any annotation.
    """
    if not isinstance(queue, dict) or queue.get('schema_version') != 1:
        raise ValueError('Expected decision queue schema 1')
    if (queue.get('analysis_status') != 'reviewed_activity_decision_queue_not_ev_ready'
            or queue.get('ready_for_equity_or_ev') is not False):
        raise ValueError('Expected EV-blocked activity decision queue')
    tasks = queue.get('tasks')
    if not isinstance(tasks, list) or len(tasks) > 10000:
        raise ValueError('Invalid or oversized task list')
    for name in ('source_review_sha256', 'recording_sha256',
                 'evidence_manifest_sha256', 'ocr_report_sha256'):
        if not isinstance(queue.get(name), str) or not _SHA.fullmatch(queue[name]):
            raise ValueError(f'Invalid {name}')
    digest = _digest(queue)
    if expected_sha256 is not None and (not isinstance(expected_sha256, str)
                                        or not _SHA.fullmatch(expected_sha256)
                                        or expected_sha256 != digest):
        raise ValueError('Queue SHA-256 mismatch')
    seen = set()
    entries, cards = [], []
    for task in tasks:
        if not isinstance(task, dict) or task.get('ready_for_ev') is not False or task.get('human_confirmed') is not False:
            raise ValueError('Task must remain unconfirmed and EV-blocked')
        table, hand, index = task.get('table_id'), task.get('hand_id'), task.get('decision_observation_index')
        if (type(table) is not int or not 1 <= table <= 4 or not isinstance(hand, str)
                or not hand or len(hand) > 200 or type(index) is not int or index < 0):
            raise ValueError('Invalid task identity')
        timestamp = _number(task.get('decision_timestamp'), 'decision_timestamp')
        key = (table, hand, index)
        if key in seen:
            raise ValueError('Duplicate task identity')
        seen.add(key)
        hints = task.get('visible_hints_unverified')
        sources = task.get('reviewed_ocr_sources')
        if not isinstance(hints, dict) or not isinstance(sources, dict):
            raise ValueError('Missing hint/source maps')
        shown = []
        for field in ('hero_cards', 'board', 'pot'):
            hint, source = hints.get(field), sources.get(field)
            if hint is None:
                if source is not None:
                    raise ValueError('Source without hint')
                shown.append((field, 'não observado antes da decisão', ''))
                continue
            if not isinstance(hint, dict) or not isinstance(source, dict):
                raise ValueError('Hint must have reviewed OCR provenance')
            source_time = _number(source.get('source_timestamp'), 'source_timestamp')
            if not source_time < timestamp or source_time != hint.get('source_timestamp'):
                raise ValueError('Source timestamp is not strictly earlier than decision')
            path = _safe_source(source.get('source_image'))
            # Source paths are TEXT, not links or file:// resources.
            value = json.dumps(hint.get('value'), ensure_ascii=False, allow_nan=False)
            shown.append((field, value, f'PTS {source_time:g}s · {path}'))
        blockers = task.get('blockers')
        if not isinstance(blockers, list) or not all(isinstance(x, str) for x in blockers):
            raise ValueError('Invalid blockers')
        entries.append({
            'table_id': table, 'hand_id': hand, 'event_index': index,
            'decision_timestamp': timestamp,
            'human_confirmed': False, 'ready_for_ev': False,
            'reviewed_fields': {field: {'value': None, 'confidence': None,
                                        'source_timestamp': None, 'source': None,
                                        'human_confirmed': False} for field in _FIELDS},
            'call_range': None, 'model_assumptions': None,
            'reviewer_notes': '',
        })
        rows = ''.join('<tr><th>'+escape(field)+'</th><td>'+escape(value)+'</td><td>'+
                       escape(source)+'</td></tr>' for field, value, source in shown)
        blocker_text = ', '.join(blockers) if blockers else 'nenhum registrado (revisão ainda obrigatória)'
        cards.append('<section><h2>Mesa '+str(table)+' · Mão '+escape(hand)+
                     ' · Evento '+str(index)+'</h2><p>Decisão em PTS '+f'{timestamp:g}'+
                     's · Ação anotada (não verificada): '+
                     escape(str(task.get('observed_action_hint', 'desconhecida')))+
                     '</p><table><thead><tr><th>Campo</th><th>Indício anterior</th><th>Origem</th></tr></thead><tbody>'+
                     rows+'</tbody></table><p>Bloqueios: '+escape(blocker_text)+'</p></section>')
    html = ('<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
            '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
            'style-src \'unsafe-inline\'; img-src \'none\'; connect-src \'none\'; '
            'form-action \'none\'; base-uri \'none\'">'
            '<title>PLO Trainee — revisão offline</title><style>'
            'body{font:16px system-ui,sans-serif;max-width:980px;margin:2rem auto;padding:0 1rem}'
            'section{border:1px solid #888;padding:1rem;margin:1rem 0;overflow-wrap:anywhere}'
            'table{border-collapse:collapse;width:100%}td,th{border:1px solid #aaa;padding:.5rem;text-align:left}'
            '</style></head><body><h1>Revisão manual — PLO5/PLO6</h1>'
            '<p><strong>NÃO EXECUTAR EQUITY/EV.</strong> Os dados abaixo são indícios '
            'de OCR revisados, não uma reconstrução visual comprovada. '
            'Confirme ações, cartas, valores, ranges e hipóteses independentemente. '
            'Este HTML não carrega imagens, scripts ou recursos externos.</p>'
            '<p>SHA-256 da fila: '+digest+'</p>'+''.join(cards)+'</body></html>')
    review = {
        'schema_version': 1,
        'analysis_status': 'manual_review_template_unconfirmed_no_ev',
        'source_queue_sha256': digest,
        'recording_sha256': queue['recording_sha256'],
        'ready_for_equity_or_ev': False,
        'source_visual_content_verified': False,
        'entries': entries,
        'warning': 'Modelo em branco; preencher campos não autentica vídeo nem autoriza EV automaticamente.',
    }
    return {'html': html, 'template': review, 'counts': {'tasks': len(entries)}}


def write_review_packet(queue_path, html_path, template_path, *, expected_sha256=None):
    source, html_file, json_file = (Path(x) for x in (queue_path, html_path, template_path))
    resolved = [x.resolve() for x in (source, html_file, json_file)]
    if len(set(resolved)) != 3 or html_file.exists() or json_file.exists():
        raise ValueError('Output paths must be new and distinct from inputs')
    packet = build_review_packet(json.loads(source.read_text(encoding='utf-8')),
                                 expected_sha256=expected_sha256)
    html_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    with html_file.open('x', encoding='utf-8') as stream:
        stream.write(packet['html'])
    with json_file.open('x', encoding='utf-8') as stream:
        json.dump(packet['template'], stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    return packet['counts']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('queue_json')
    parser.add_argument('output_html')
    parser.add_argument('output_template_json')
    parser.add_argument('--expected-sha256')
    args = parser.parse_args()
    print(json.dumps(write_review_packet(args.queue_json, args.output_html,
                                         args.output_template_json,
                                         expected_sha256=args.expected_sha256)))