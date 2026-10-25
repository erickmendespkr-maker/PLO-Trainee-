"""Offline, unapproved human-review handoff for a completed evidence job.

Only audits provenance and binds OCR hints to audited frames. Never confirms
cards/actions, reconstructs hands, computes equity/EV or chooses clips.
"""
import argparse
from collections import defaultdict
import hashlib
from html import escape
import json
import math
from pathlib import Path
import re
import tempfile

from offline_job_evidence_audit import audit_job, _json, MAX_JSON_BYTES
from offline_jobs import OfflineJobStore

FRAME_NAME = re.compile(r'^table_(0[1-4])/frame_(\d{5})\.png$')
FIELDS = frozenset(('pot', 'bet', 'board', 'hero_cards'))
MAX_PREVIEWS = 120


def _hash(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _same_stamp(left, right):
    return type(left) in (int, float) and type(right) in (int, float) and (
        math.isfinite(left) and math.isfinite(right) and abs(left - right) < 1e-6)


def build_handoff(store, job_id, results_root):
    """Return a read-only, unapproved review index; fail closed on mismatches."""
    audited = audit_job(store, job_id, results_root)
    folder = Path(results_root) / job_id
    manifest = _json(folder / 'manifest.json')
    result = _json(folder / 'result.json')
    interval = manifest['interval_seconds']
    indexed = {}
    counts = defaultdict(int)
    hash_covered = 0
    for frame, original in zip(audited['frames'], manifest['frames']):
        if original.get('sha256') is not None:
            expected = original['sha256']
            if type(expected) is not str or not re.fullmatch(r'[0-9a-f]{64}', expected) or expected != frame['sha256']:
                raise ValueError('Frame SHA-256 differs from manifest')
            hash_covered += 1
        match = FRAME_NAME.fullmatch(frame['image'])
        if not match or int(match.group(1)) != frame['table_id']:
            raise ValueError('Invalid frame index')
        sequence = int(match.group(2))
        table = frame['table_id']
        if sequence != counts[table] or not _same_stamp(frame['nominal_timestamp_seconds'], sequence * interval):
            raise ValueError('Nonsequential frame or mismatched nominal timestamp')
        counts[table] += 1
        indexed[(table, float(frame['nominal_timestamp_seconds']))] = frame

    hints = defaultdict(list)
    ocr_sha = None
    template_sha = audited['review_template_sha256']
    if result.get('review_template') is not None:
        ocr_path = folder / 'ocr_candidates.json'
        report = _json(ocr_path)
        if (type(report) is not dict or report.get('schema_version') != 1 or
                report.get('analysis_status') != 'unverified_ocr_candidates_only' or
                report.get('requires_manual_review') is not True or
                type(report.get('candidates')) is not list or
                len(report['candidates']) != result.get('ocr_candidates')):
            raise ValueError('OCR report does not match worker summary')
        ocr_sha = _hash(ocr_path)
        template = _json(folder / 'review_template.json')
        if (type(template) is not dict or template.get('schema_version') != 1 or
                template.get('analysis_status') != 'unapproved_human_review_template' or
                template.get('requires_manual_review') is not True or
                type(template.get('events')) is not list):
            raise ValueError('Invalid review template')
        candidate_keys = {}
        for idx, item in enumerate(report['candidates']):
            if type(item) is not dict or item.get('status') not in ('candidate_unverified', 'needs_manual_review'):
                raise ValueError('Unexpected OCR candidate status')
            table, stamp, field = item.get('table_id'), item.get('timestamp'), item.get('field')
            if type(table) is not int or field not in FIELDS or not _same_stamp(stamp, stamp):
                raise ValueError('Invalid OCR candidate')
            key = (table, float(stamp))
            frame = indexed.get(key)
            if frame is None or item.get('source_image') != frame['image']:
                raise ValueError('OCR candidate not bound to audited frame')
            identity = (table, float(stamp), field)
            if identity in candidate_keys:
                raise ValueError('Duplicate OCR field')
            candidate_keys[identity] = idx
            hints[key].append({'field': field, 'candidate_index': idx,
                               'status': item['status'], 'unverified_text': str(item.get('parsed_candidate'))[:200]})
        reviewed = set()
        for event in template['events']:
            if type(event) is not dict or event.get('human_confirmed') is not False or event.get('hand_id') is not None:
                raise ValueError('Review template contains approved/assigned events')
            table, stamp = event.get('table_id'), event.get('timestamp')
            if type(table) is not int or not _same_stamp(stamp, stamp):
                raise ValueError('Invalid review event timestamp')
            fields = event.get('field_reviews')
            if type(fields) is not dict or not fields:
                raise ValueError('Invalid review event fields')
            for field, review in fields.items():
                identity = (table, float(stamp), field)
                if (identity not in candidate_keys or identity in reviewed or
                        type(review) is not dict or type(review.get('candidate_index')) is not int or
                        review['candidate_index'] != candidate_keys[identity] or
                        review.get('human_confirmed') is not False or
                        review.get('approved_value') is not None):
                    raise ValueError('Review field does not match unapproved OCR')
                reviewed.add(identity)
        if reviewed != set(candidate_keys):
            raise ValueError('Review template omits OCR candidates')
    elif result.get('ocr_candidates') not in (0, None):
        raise ValueError('OCR candidates exist without a review template')

    frames = [{**frame, 'ocr_hints_unverified': hints.get((frame['table_id'],
              float(frame['nominal_timestamp_seconds'])), [])} for frame in audited['frames']]
    return {'schema_version': 1, 'analysis_status': 'unapproved_offline_review_handoff',
            'job_id': job_id, 'requires_manual_review': True,
            'timestamp_semantics': 'nominal_sampling_grid_not_exact_source_pts',
            'source_sha256': audited['recording_sha256'],
            'worker_result_sha256': audited['worker_result_sha256'],
            'evidence_manifest_sha256': audited['evidence_manifest_sha256'],
            'review_template_sha256': template_sha, 'ocr_candidates_sha256': ocr_sha,
            'frame_count': len(frames), 'table_frame_counts': dict(audited['table_frame_counts']),
            'manifest_frame_hashes_matched': hash_covered == len(frames),
            'ocr_hint_count': sum(len(v) for v in hints.values()), 'frames': frames,
            'hand_reconstruction_verified': False, 'ready_for_equity_or_ev': False,
            'automatic_clip_selection_authorized': False,
            'limitations': ['File hashes attest bytes only; no trusted baseline for original frames.',
                            'Frame timestamps are nominal, not independently verified source PTS.',
                            'OCR hints are unverified; human review of cards/actions is mandatory.']}


def render_html(handoff):
    """Static HTML; references local PNGs without embedding large video data."""
    frames = handoff['frames']
    # Deterministic, bounded overview for long recordings.
    if len(frames) > MAX_PREVIEWS:
        indices = sorted({round(i * (len(frames) - 1) / (MAX_PREVIEWS - 1)) for i in range(MAX_PREVIEWS)})
        preview = [frames[i] for i in indices]
    else:
        preview = frames
    cards = []
    for frame in preview:
        image = escape('../' + frame['image'], quote=True)
        caption = f"Mesa {frame['table_id']} · {frame['nominal_timestamp_seconds']:.2f}s (nominal)"
        hints = ', '.join(escape(h['field']) for h in frame['ocr_hints_unverified']) or 'Sem OCR'
        cards.append(f'<figure><img loading="lazy" src="{image}" alt="{escape(caption)}">'
                     f'<figcaption>{escape(caption)} · {hints} · não verificado</figcaption></figure>')
    return ('<!doctype html><html lang="pt-BR"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>PLO Trainee — evidências não verificadas</title>'
            '<style>body{font:16px system-ui;margin:2rem;background:#151b22;color:#f1f4f8}'
            'main{max-width:1200px;margin:auto}section{display:grid;grid-template-columns:'
            'repeat(auto-fit,minmax(230px,1fr));gap:12px}figure{margin:0;background:#25303b;padding:8px}'
            'img{width:100%;height:auto}figcaption{font-size:13px}a{color:#aaddff}</style>'
            '<main><h1>Revisão humana pendente</h1><p>Quadros e OCR não confirmam mãos, '
            'cartas ou ações. Timestamps nominais, não PTS certificados.</p>'
            f'<p>{len(frames)} quadros auditados; exibindo {len(preview)}. '
            '<a href="review_handoff.json">Índice JSON completo</a>.</p>'
            '<section>' + ''.join(cards) + '</section></main></html>')


def export_handoff(store, job_id, results_root):
    """Write once in a job-local new directory; leave the queue untouched."""
    report = build_handoff(store, job_id, results_root)
    folder = Path(results_root) / job_id
    target = folder / 'review_handoff'
    if target.exists() or target.is_symlink():
        raise FileExistsError('Review handoff already exists')
    with tempfile.TemporaryDirectory(prefix='.review_handoff_', dir=folder) as temp:
        tmp = Path(temp)
        (tmp / 'review_handoff.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
        (tmp / 'index.html').write_text(render_html(report), encoding='utf-8')
        tmp.rename(target)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('database')
    parser.add_argument('job_id')
    parser.add_argument('results_root')
    parser.add_argument('--export', action='store_true', help='Write new job-local HTML and JSON')
    args = parser.parse_args(argv)
    store = OfflineJobStore(args.database)
    report = (export_handoff if args.export else build_handoff)(store, args.job_id, args.results_root)
    print(json.dumps({'job_id': report['job_id'], 'frame_count': report['frame_count'],
                      'ocr_hint_count': report['ocr_hint_count'], 'manual_review_required': True}))


if __name__ == '__main__':
    main()
