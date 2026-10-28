"""Record offline, human-supplied observations without promoting model EV to fact.

Usage:
  python video_analyzer/offline_human_observation_review.py \
      recording.mp4 exported_batch/ session_review.json manual_annotations.json \
      new_review.json new_review.html

The manual_annotations.json is created by a person, NOT inferred from the video.
No poker service, account, network, live analysis, or automatic correction is used.
This tool does not authenticate the reviewer or independently verify observations.
"""
from __future__ import annotations

import argparse
from decimal import Decimal
import hashlib
from html import escape
import json
import math
import os
from pathlib import Path
import re
import tempfile

MAX_JSON = 4 * 1024 * 1024
MAX_DECISIONS = 32
SHA = re.compile(r'[0-9a-f]{64}\Z')
ALIAS = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{2,47}\Z')
SAFE_NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z')
ACTIONS = ('fold', 'call', 'raise')
OUTCOMES = ('confirmed', 'corrected', 'inconclusive')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), 'Missing or symlinked input')
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def unique(pairs):
    out = {}
    for key, value in pairs:
        require(key not in out, 'Duplicate JSON key')
        out[key] = value
    return out


def load(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink() and
            0 < path.stat().st_size <= MAX_JSON, 'Invalid JSON input')
    return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=unique,
                      parse_constant=lambda val: (_ for _ in ()).throw(ValueError(val)))


def timestamp(value):
    require(type(value) in (float, int) and math.isfinite(value) and value >= 0,
            'Invalid timestamp')
    return float(value)


def identifier(value, maximum=1000):
    return type(value) is str and 1 <= len(value) <= maximum and not any(
        ord(ch) < 32 or ord(ch) == 127 for ch in value)


def key_of(item):
    require(type(item) is dict and type(item.get('table_id')) is int and
            1 <= item['table_id'] <= 4 and identifier(item.get('hand_id'), 64) and
            identifier(item.get('decision_id')), 'Invalid decision identity')
    return item['table_id'], item['hand_id'], item['decision_id']


def verify_source(manifest, video_hash, clips):
    require(type(manifest) is dict and manifest.get('schema_version') == 1 and
            manifest.get('analysis_status') == 'offline_read_only_human_review_packet' and
            manifest.get('source_recording_sha256') == video_hash and
            manifest.get('human_review_recorded') is False and
            manifest.get('video_evidence_independently_verified') is False and
            manifest.get('range_assumptions_verified') is False and
            manifest.get('decision_quality_verified') is False and
            manifest.get('automatic_clip_selection_authorized') is False and
            manifest.get('action_recommendation_authorized') is False and
            manifest.get('clip_media_hashes_rechecked') is True and
            manifest.get('ffprobe_media_checked') is True and
            type(manifest.get('decisions')) is list and
            1 <= len(manifest['decisions']) <= MAX_DECISIONS and
            type(manifest.get('decision_count')) is int and
            manifest['decision_count'] == len(manifest['decisions']),
            'Unsupported or promoted session review packet')
    source = {}
    media = {}
    for item in manifest['decisions']:
        key = key_of(item)
        require(key not in source and item.get('game_type') in ('PLO5', 'PLO6') and
                item.get('observed_action') in ACTIONS and
                item.get('human_review_status') == 'pending' and
                item.get('model_conditional_only') is True and
                item.get('decision_quality_verified') is False,
                'Invalid or duplicated source decision')
        name = item.get('clip_file')
        require(type(name) is str and SAFE_NAME.fullmatch(name) and name.endswith('.mp4') and
                type(item.get('clip_sha256')) is str and SHA.fullmatch(item['clip_sha256']),
                'Unsafe clip reference')
        path = clips / name
        require(path.is_file() and not path.is_symlink() and path.parent == clips,
                'Missing or symlinked clip')
        if name not in media:
            media[name] = sha256(path)
        require(media[name] == item['clip_sha256'], 'Clip hash mismatch')
        hand = item.get('candidate_window_seconds')
        clip = item.get('clip_window_seconds')
        require(type(hand) is list and len(hand) == 2 and
                type(clip) is list and len(clip) == 2, 'Invalid source windows')
        hs, he = map(timestamp, hand)
        cs, ce = map(timestamp, clip)
        original = timestamp(item.get('action_pts_seconds'))
        require(cs <= hs <= original <= he <= ce and hs < he,
                'Source timestamp outside clip or hand')
        source[key] = item
    require(type(manifest.get('clip_count')) is int and
            manifest['clip_count'] == len(media), 'Source clip count mismatch')
    return source, media


def validate_annotations(annotations, source, source_hash):
    require(type(annotations) is dict and set(annotations) == {
                'schema_version', 'source_session_review_sha256', 'reviewer_alias', 'entries'} and
            annotations['schema_version'] == 1 and
            annotations['source_session_review_sha256'] == source_hash and
            type(annotations['reviewer_alias']) is str and
            ALIAS.fullmatch(annotations['reviewer_alias']) and
            type(annotations['entries']) is list and
            1 <= len(annotations['entries']) <= len(source),
            'Invalid manual annotations or source binding')
    checked = {}
    for entry in annotations['entries']:
        require(type(entry) is dict and set(entry) == {
                    'table_id', 'hand_id', 'decision_id', 'outcome',
                    'corrected_observed_action', 'corrected_action_pts_seconds', 'note'},
                'Invalid manual annotation fields')
        key = key_of(entry)
        require(key in source and key not in checked, 'Unknown or duplicate reviewed decision')
        outcome = entry['outcome']
        note = entry['note']
        require(outcome in OUTCOMES and type(note) is str and
                len(note) <= 1000 and not any(ord(ch) < 32 and ch not in '\n\t'
                                               for ch in note), 'Invalid outcome or note')
        original = source[key]
        action = entry['corrected_observed_action']
        time = entry['corrected_action_pts_seconds']
        if outcome == 'corrected':
            require(action in ACTIONS and time is not None and len(note.strip()) >= 10,
                    'Corrections require action, timestamp and explanation')
            time = timestamp(time)
            hs, he = map(timestamp, original['candidate_window_seconds'])
            cs, ce = map(timestamp, original['clip_window_seconds'])
            require(cs <= hs <= time <= he <= ce and
                    (action != original['observed_action'] or
                     time != timestamp(original['action_pts_seconds'])),
                    'Correction must change observation within reviewed hand')
        else:
            require(action is None and time is None,
                    'Confirmed/inconclusive decisions cannot carry corrections')
            if outcome == 'inconclusive':
                require(len(note.strip()) >= 10, 'Inconclusive review needs explanation')
        checked[key] = {
            'table_id': key[0], 'hand_id': key[1], 'decision_id': key[2],
            'outcome': outcome, 'note': note,
            'corrected_observed_action': action,
            'corrected_action_pts_seconds': time,
        }
    return checked


def render_html(report, batch_name):
    h = lambda val: escape(str(val), quote=True)
    cards = []
    for row in report['decisions']:
        clip = h(batch_name + '/' + row['clip_file'])
        reviewed = row['review']
        if reviewed is None:
            summary = 'Pendente de revisão humana'
        else:
            summary = 'Anotação fornecida: ' + h(reviewed['outcome'])
        details = ''
        if reviewed is not None:
            details = ('<p>Observação anotada: ' + h(reviewed['corrected_observed_action']
                       if reviewed['outcome'] == 'corrected' else row['original_observed_action']) +
                       ' · Timestamp: ' + h(reviewed['corrected_action_pts_seconds']
                       if reviewed['outcome'] == 'corrected' else row['original_action_pts_seconds']) +
                       's</p><p>Nota: ' + h(reviewed['note']) + '</p>')
        cards.append('<article><h2>Mesa ' + str(row['table_id']) + ' · ' +
                     h(row['game_type']) + ' · ' + h(row['hand_id']) + '</h2>' +
                     '<video controls preload="none" src="' + clip + '"></video>' +
                     '<p>Decisão: ' + h(row['decision_id']) + ' · ' + summary + '</p>' +
                     '<p>Observação original: ' + h(row['original_observed_action']) +
                     ' aos ' + h(row['original_action_pts_seconds']) + 's</p>' + details +
                     '<p class="warn">Revisão humana declarada, não autenticada. EV e ranges não recalculados.</p></article>')
    return ('''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; media-src 'self' file:; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>PLO Trainee — revisão registrada</title>
<style>body{font:16px system-ui;background:#111827;color:#f3f4f6;max-width:960px;margin:2rem auto;padding:0 1rem}article{background:#1f2937;border:1px solid #4b5563;border-radius:12px;padding:1rem;margin:1rem 0}video{max-width:100%;width:440px}.warn{color:#fcd34d}</style>
</head><body><h1>Revisões de observações — offline</h1><p>Não há verificação de identidade humana, OCR, ranges ou qualidade da jogada. As anotações não alteram os arquivos de origem.</p>'''
            + '\n'.join(cards) + '</body></html>\n')


def build(recording, clip_directory, source_json, annotations_json, output_json, output_html):
    recording, clips, source_path, manual_path, output, html = map(Path, (
        recording, clip_directory, source_json, annotations_json, output_json, output_html))
    require(clips.is_dir() and not clips.is_symlink() and SAFE_NAME.fullmatch(clips.name) and
            output.parent == html.parent == clips.parent and output.suffix == '.json' and
            html.suffix == '.html' and output != html and
            all(not p.exists() and not p.is_symlink() for p in (output, html)) and
            len({str(p.resolve()) for p in (recording, source_path, manual_path,
                                           output, html)}) == 5,
            'Outputs must be new sibling files, without overwrites')
    hashes = {str(p): sha256(p) for p in (recording, source_path, manual_path)}
    manifest = load(source_path)
    source, media = verify_source(manifest, hashes[str(recording)], clips)
    manual = load(manual_path)
    reviewed = validate_annotations(manual, source, hashes[str(source_path)])
    rows = []
    for key, original in source.items():
        rows.append({
            'table_id': key[0], 'hand_id': key[1], 'decision_id': key[2],
            'game_type': original['game_type'], 'clip_file': original['clip_file'],
            'clip_sha256': original['clip_sha256'],
            'original_observed_action': original['observed_action'],
            'original_action_pts_seconds': original['action_pts_seconds'],
            'original_review_label': original.get('review_label'),
            'model_conditional_only': True, 'decision_quality_verified': False,
            'review': reviewed.get(key),
        })
    report = {
        'schema_version': 1,
        'analysis_status': 'offline_human_supplied_observation_review_unverified',
        'source_recording_sha256': hashes[str(recording)],
        'source_session_review_sha256': hashes[str(source_path)],
        'source_manual_annotations_sha256': hashes[str(manual_path)],
        'reviewer_alias_unverified': manual['reviewer_alias'],
        'reviewed_decision_count': len(reviewed),
        'pending_decision_count': len(rows) - len(reviewed),
        'decision_count': len(rows),
        'clip_count': len(media),
        'human_supplied_annotations_recorded': True,
        'reviewer_identity_authenticated': False,
        'video_evidence_independently_verified': False,
        'range_assumptions_verified': False,
        'equity_ev_recomputed': False,
        'decision_quality_verified': False,
        'automatic_clip_selection_authorized': False,
        'action_recommendation_authorized': False,
        'source_files_modified': False,
        'warning': ('Anotacoes fornecidas externamente, sem autenticacao humana nem '
                    'verificacao independente de cartas/acoes. Corrigir observacoes '
                    'invalida analises dependentes; recalcular EV antes de interpretar.'),
        'decisions': rows,
    }
    page = render_html(report, clips.name)
    # Recheck all sources and media before publishing; outputs are new files.
    require(all(sha256(Path(p)) == value for p, value in hashes.items()) and
            all(sha256(clips / name) == value for name, value in media.items()),
            'Source changed during review processing')
    with tempfile.TemporaryDirectory(prefix='plo_manual_review_', dir=clips.parent) as tmp:
        staged_json, staged_html = Path(tmp) / 'review.json', Path(tmp) / 'review.html'
        staged_json.write_text(json.dumps(report, ensure_ascii=False, indent=2,
                                          allow_nan=False) + '\n', encoding='utf-8')
        staged_html.write_text(page, encoding='utf-8')
        os.link(staged_json, output)
        try:
            os.link(staged_html, html)
        except BaseException:
            output.unlink()
            raise
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('recording', 'clip_directory', 'source_json', 'annotations_json',
                 'output_json', 'output_html'):
        parser.add_argument(name)
    args = parser.parse_args(argv)
    result = build(*(getattr(args, key) for key in (
        'recording', 'clip_directory', 'source_json', 'annotations_json',
        'output_json', 'output_html')))
    print(json.dumps({'status': result['analysis_status'],
                      'reviewed': result['reviewed_decision_count'],
                      'pending': result['pending_decision_count']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())