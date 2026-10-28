"""Generate an entirely OFFLINE, read-only HTML/JSON review packet from Cycle 162.

Usage:
 python video_analyzer/offline_session_review_dashboard.py \
   recording.mp4 exported_batch/ manual_review_priority.json \
   session_review.json session_review.html

The HTML previews *already manually selected* clips. It never selects clips,
recommends actions, asserts a poker error, accesses a network, or edits media.
Only integrity and schema consistency are checked; observations remain hypotheses.
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
import subprocess
import tempfile

MAX_JSON = 4 * 1024 * 1024
MAX_DECISIONS = 32
MAX_CLIPS = 12
SAFE_NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z')
SHA = re.compile(r'[0-9a-f]{64}\Z')
AMOUNT = re.compile(r'-?(?:0|[1-9][0-9]{0,15})(?:\.[0-9]{1,8})?\Z')
LABELS = ('model_interval_separated_manual_review',
          'overlapping_intervals_manual_review', 'no_positive_model_gap_detected')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(path):
    p = Path(path)
    require(p.is_file() and not p.is_symlink(), 'Missing or symlinked input')
    h = hashlib.sha256()
    with p.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'Duplicate JSON key')
        result[key] = value
    return result


def read(path):
    p = Path(path)
    require(p.is_file() and not p.is_symlink() and 0 < p.stat().st_size <= MAX_JSON,
            'Invalid input JSON')
    return json.loads(p.read_text(encoding='utf-8'), object_pairs_hook=unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def money(value):
    require(type(value) is str and AMOUNT.fullmatch(value), 'Invalid decimal value')
    return Decimal(value)


def time_value(value):
    require(type(value) in (int, float) and math.isfinite(value) and value >= 0,
            'Invalid timestamp')
    return float(value)


def sha(value):
    return type(value) is str and SHA.fullmatch(value) is not None


def check_video(path):
    """Reject corrupt/non-video clips before creating a clickable local preview."""
    try:
        result = subprocess.run([
            'ffprobe', '-v', 'error', '-select_streams', 'v:0',
            '-show_entries', 'stream=codec_type,width,height:format=duration',
            '-of', 'json', str(path)], capture_output=True, text=True,
            timeout=15, check=True)
        data = json.loads(result.stdout)
        streams = data.get('streams', [])
        require(len(streams) == 1 and streams[0].get('codec_type') == 'video' and
                type(streams[0].get('width')) is int and streams[0]['width'] > 0 and
                type(streams[0].get('height')) is int and streams[0]['height'] > 0,
                'MP4 has no valid video stream')
        duration = float(data.get('format', {}).get('duration', 'nan'))
        require(math.isfinite(duration) and duration > 0, 'Invalid MP4 duration')
        return {'duration_seconds': round(duration, 3),
                'width': streams[0]['width'], 'height': streams[0]['height']}
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired,
            ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise ValueError('FFprobe failed to validate MP4') from exc


def validate_queue(priority, video_sha, directory):
    require(type(priority) is dict and priority.get('schema_version') == 1 and
            priority.get('analysis_status') == 'offline_hypothetical_ev_manual_review_priority_only' and
            priority.get('source_recording_sha256') == video_sha and
            sha(priority.get('source_ev_attachments_sha256')) and
            priority.get('video_evidence_independently_verified') is False and
            priority.get('range_assumptions_verified') is False and
            priority.get('decision_quality_verified') is False and
            priority.get('automatic_clip_selection_authorized') is False and
            priority.get('action_recommendation_authorized') is False and
            priority.get('clip_media_hashes_rechecked') is True and
            priority.get('original_ev_sources_recomputed_in_this_step') is False and
            type(priority.get('manual_review_queue')) is list and
            1 <= len(priority['manual_review_queue']) <= MAX_DECISIONS and
            type(priority.get('decision_count')) is int and
            priority['decision_count'] == len(priority['manual_review_queue']) and
            type(priority.get('clip_count')) is int and
            1 <= priority['clip_count'] <= MAX_CLIPS,
            'Unsupported or promoted priority report')
    threshold = money(priority.get('min_conditional_interval_separation_units'))
    require(threshold >= 0, 'Negative threshold')
    seen_decisions, seen_clips, seen_hands, clip_hashes, media = set(), {}, {}, {}, {}
    rows = []
    for row in priority['manual_review_queue']:
        require(type(row) is dict and type(row.get('table_id')) is int and
                1 <= row['table_id'] <= 4 and
                type(row.get('hand_id')) is str and 1 <= len(row['hand_id']) <= 64 and
                type(row.get('decision_id')) is str and 1 <= len(row['decision_id']) <= 1000 and
                row.get('game_type') in ('PLO5', 'PLO6') and
                row.get('observed_action') in ('fold', 'call', 'raise') and
                row.get('review_label') in LABELS and
                row.get('range_hypotheses_not_verified') is True and
                row.get('model_sampling_bounds_not_total_uncertainty') is True and
                row.get('human_review_required') is True and
                row.get('decision_quality_verified') is False and
                row.get('automatic_clip_selection_authorized') is False and
                row.get('action_recommendation_authorized') is False and
                sha(row.get('source_ev_report_sha256')) and
                sha(row.get('source_reviewed_decision_ev_link_sha256')) and
                type(row.get('call_range_assumption')) is str and
                bool(row['call_range_assumption'].strip()) and
                type(row.get('raise_called_range_assumption')) is str and
                bool(row['raise_called_range_assumption'].strip()),
                'Invalid or promoted review decision')
        key = (row['table_id'], row['hand_id'], row['decision_id'])
        require(key not in seen_decisions, 'Duplicate review decision')
        seen_decisions.add(key)
        filename = row.get('clip_file')
        require(type(filename) is str and SAFE_NAME.fullmatch(filename) and
                filename.endswith('.mp4') and sha(row.get('clip_sha256')),
                'Unsafe clip reference')
        clip = directory / filename
        require(clip.is_file() and not clip.is_symlink() and clip.parent == directory,
                'Missing or symlinked MP4')
        if filename not in clip_hashes:
            clip_hashes[filename] = digest(clip)
            media[filename] = check_video(clip)
        require(clip_hashes[filename] == row['clip_sha256'], 'MP4 hash mismatch')
        hand_key = (row['table_id'], row['hand_id'])
        require(filename not in seen_clips or seen_clips[filename] == hand_key,
                'MP4 assigned to multiple hands')
        seen_clips[filename] = hand_key
        require(hand_key not in seen_hands or seen_hands[hand_key] == filename,
                'Hand assigned to multiple MP4s')
        seen_hands[hand_key] = filename
        hw, cw = row.get('candidate_window_seconds'), row.get('clip_window_seconds')
        require(type(hw) is list and len(hw) == 2 and
                type(cw) is list and len(cw) == 2, 'Missing hand/clip windows')
        hs, he = map(time_value, hw)
        cs, ce = map(time_value, cw)
        t = time_value(row.get('action_pts_seconds'))
        require(cs <= hs <= t <= he <= ce and hs < he and
                hs - cs <= 15 and ce - he <= 15,
                'Decision/hand/clip timestamp mismatch')
        require(abs(media[filename]['duration_seconds'] - (ce-cs)) <= 0.75,
                'Exported MP4 duration differs from reported clip window')
        low = money(row.get('positive_interval_separation_units'))
        high = money(row.get('possible_gap_upper_units'))
        require(0 <= low <= high, 'Inconsistent EV gap bounds')
        observed = row.get('observed_ev_interval_units')
        require(type(observed) is list and len(observed) == 2 and
                money(observed[0]) <= money(observed[1]), 'Invalid observed EV interval')
        label = row['review_label']
        require((label == LABELS[0] and low > threshold) or
                (label == LABELS[1] and low <= threshold and high > threshold) or
                (label == LABELS[2] and high <= threshold),
                'Review label conflicts with supplied conditional bounds')
        require(0 <= money(row.get('fold_probability_hypothesis')) <= 1,
                'Invalid fold probability')
        rows.append({
            'table_id': row['table_id'], 'hand_id': row['hand_id'],
            'decision_id': row['decision_id'], 'game_type': row['game_type'],
            'clip_file': filename, 'clip_sha256': clip_hashes[filename],
            'clip_window_seconds': [cs, ce], 'candidate_window_seconds': [hs, he],
            'action_pts_seconds': t, 'observed_action': row['observed_action'],
            'review_label': label, 'positive_interval_separation_units': str(low),
            'possible_gap_upper_units': str(high),
            'observed_ev_interval_units': observed,
            'fold_probability_hypothesis': row['fold_probability_hypothesis'],
            'call_range_assumption': row['call_range_assumption'],
            'raise_called_range_assumption': row['raise_called_range_assumption'],
            'media': media[filename], 'human_review_status': 'pending',
            'model_conditional_only': True, 'decision_quality_verified': False,
            'source_ev_report_sha256': row['source_ev_report_sha256'],
            'source_reviewed_decision_ev_link_sha256':
                row['source_reviewed_decision_ev_link_sha256'],
        })
    require(len(seen_clips) == priority['clip_count'], 'Clip count mismatch')
    return rows, clip_hashes


def render_html(manifest, batch_name):
    def h(value):
        return escape(str(value), quote=True)
    cards = []
    for index, row in enumerate(manifest['decisions'], 1):
        clip_url = h(batch_name + '/' + row['clip_file'])
        cards.append(f'''<article class="card">
<h2>#{index} · Mesa {row['table_id']} · {h(row['game_type'])} · {h(row['hand_id'])}</h2>
<p><strong>Revisão:</strong> {h(row['review_label'])} · <strong>Ação observada:</strong> {h(row['observed_action'])}</p>
<video controls preload="none" playsinline width="480" src="{clip_url}">Prévia MP4 local indisponível.</video>
<p>Decisão aos {h(row['action_pts_seconds'])}s · Intervalo da mão: {h(row['candidate_window_seconds'][0])}–{h(row['candidate_window_seconds'][1])}s</p>
<p>Separação inferior condicional: {h(row['positive_interval_separation_units'])} · Diferença superior possível: {h(row['possible_gap_upper_units'])}</p>
<p>Intervalo EV observado: {h(row['observed_ev_interval_units'][0])} a {h(row['observed_ev_interval_units'][1])} fichas</p>
<details><summary>Hipóteses e proveniência</summary>
<p>Range call: {h(row['call_range_assumption'])}</p>
<p>Range raise pago: {h(row['raise_called_range_assumption'])}</p>
<p>Probabilidade hipotética de fold: {h(row['fold_probability_hypothesis'])}</p>
<p>SHA-256 do clipe: <code>{h(row['clip_sha256'])}</code></p>
<p>SHA-256 da análise EV: <code>{h(row['source_ev_report_sha256'])}</code></p>
</details><p class="notice">Pendente de revisão humana. Sem recomendação de jogada e sem erro comprovado.</p>
</article>''')
    return '''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; media-src 'self' file:; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>PLO Trainee — revisão offline</title><style>
body{font:16px system-ui,sans-serif;max-width:1000px;margin:2rem auto;padding:0 1rem;background:#111827;color:#f3f4f6}
h1,h2{line-height:1.25}h2{font-size:1.1rem}.card{border:1px solid #4b5563;border-radius:12px;padding:1rem;margin:1rem 0;background:#1f2937}
video{max-width:100%;background:#000;border-radius:8px}code{overflow-wrap:anywhere}details{margin:.7rem 0}.notice{color:#fcd34d}
</style></head><body><h1>PLO Trainee — revisão de sessão gravada</h1>
<p><strong>Somente offline.</strong> Clipes previamente exportados e selecionados manualmente. As hipóteses de ranges, OCR e EV não foram autenticadas. Intervalos Monte Carlo não cobrem incerteza do modelo. Nenhuma classificação é prova de erro.</p>
<p>Decisões para revisão: ''' + str(manifest['decision_count']) + ''' · Clipes: ''' + str(manifest['clip_count']) + '''</p>\n''' + '\n'.join(cards) + '\n</body></html>\n'


def build(recording_path, batch_directory, priority_path, output_json, output_html):
    recording, batch, source, out_json, out_html = map(Path, (
        recording_path, batch_directory, priority_path, output_json, output_html))
    require(batch.is_dir() and not batch.is_symlink() and
            type(batch.name) is str and SAFE_NAME.fullmatch(batch.name) and
            out_json.parent == batch.parent == out_html.parent and
            out_json.suffix == '.json' and out_html.suffix == '.html' and
            out_json != out_html and
            all(not p.exists() and not p.is_symlink() for p in (out_json, out_html)) and
            len({str(p.resolve()) for p in (recording, source, out_json, out_html)}) == 4,
            'Outputs must be new siblings of a safe batch directory')
    video_sha, source_sha = digest(recording), digest(source)
    priority = read(source)
    decisions, clip_hashes = validate_queue(priority, video_sha, batch)
    require(digest(recording) == video_sha and digest(source) == source_sha and
            all(digest(batch / name) == value for name, value in clip_hashes.items()),
            'Input changed while building review packet')
    manifest = {
        'schema_version': 1,
        'analysis_status': 'offline_read_only_human_review_packet',
        'source_recording_sha256': video_sha,
        'source_manual_review_priority_sha256': source_sha,
        'source_ev_attachments_sha256': priority['source_ev_attachments_sha256'],
        'clip_count': len(clip_hashes), 'decision_count': len(decisions),
        'clip_media_hashes_rechecked': True, 'ffprobe_media_checked': True,
        'video_evidence_independently_verified': False,
        'range_assumptions_verified': False, 'decision_quality_verified': False,
        'automatic_clip_selection_authorized': False,
        'action_recommendation_authorized': False,
        'human_review_recorded': False,
        'warning': ('Somente fila para revisao humana. Intervalos de EV condicionais nao '
                    'comprovam erro; OCR, ranges, potes, apostas futuras e acao legal '
                    'nao foram autenticados. Nenhum clipe foi selecionado automaticamente.'),
        'decisions': decisions,
    }
    html = render_html(manifest, batch.name)
    with tempfile.TemporaryDirectory(prefix='plo_session_review_', dir=batch.parent) as tmp:
        staged_json, staged_html = Path(tmp) / 'review.json', Path(tmp) / 'review.html'
        staged_json.write_text(json.dumps(manifest, ensure_ascii=False, indent=2,
                                          allow_nan=False) + '\n', encoding='utf-8')
        staged_html.write_text(html, encoding='utf-8')
        os.link(staged_json, out_json)
        try:
            os.link(staged_html, out_html)
        except BaseException:
            out_json.unlink()
            raise
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('recording')
    parser.add_argument('batch_directory')
    parser.add_argument('priority_json')
    parser.add_argument('new_report_json')
    parser.add_argument('new_report_html')
    args = parser.parse_args(argv)
    result = build(args.recording, args.batch_directory, args.priority_json,
                   args.new_report_json, args.new_report_html)
    print(json.dumps({'status': result['analysis_status'],
                      'decisions': result['decision_count'],
                      'clips': result['clip_count']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
