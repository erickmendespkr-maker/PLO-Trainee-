"""Audited offline contact sheet for *unconfirmed* PLO inter-hand review windows.

Joins a boundary seek plan with FFmpeg decoded-PTS PNG evidence. This module
never detects cards/actions, asserts hand boundaries, or authorizes EV/clips.
"""
import argparse
from collections import Counter
import hashlib
from html import escape
import json
import math
from pathlib import Path
import re
import shutil
import tempfile

from activity_evidence_export import audit_activity_evidence
from activity_snapshot_chain import canonical_sha256

_SHA = re.compile(r'[0-9a-f]{64}\Z')
_IMAGE = re.compile(r'table_(0[1-4])/frame_\d{5}\.png\Z')


def _sha_file(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def _number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def build_boundary_contact_sheet(plan, manifest, evidence_root, *, max_images=600):
    """Cross-check all requested seeks, hashes, decoded PTS and window mapping.

    Returns a review-only JSON document. Missing seeks are explicit; decoded
    timestamps outside the candidate interval are flagged, not silently used
    as exact boundary evidence. All images must be locally audited first.
    """
    if type(max_images) is not int or not 1 <= max_images <= 600:
        raise ValueError('Invalid image limit')
    if (not isinstance(plan, dict) or plan.get('schema_version') != 1
            or plan.get('analysis_status') != 'requested_offline_seek_plan_only'
            or plan.get('requires_manual_review') is not True
            or plan.get('timestamp_semantics') != 'requested_seek_seconds_not_decoded_source_pts'
            or any(plan.get(k) is not False for k in (
                'automatic_hand_boundaries_authorized',
                'automatic_clip_selection_authorized', 'ready_for_equity_or_ev',
                'strategic_error_established'))
            or not isinstance(manifest, dict)):
        raise ValueError('Incompatible or prematurely authorized seek plan')
    if (not isinstance(plan.get('recording_sha256'), str)
            or not _SHA.fullmatch(plan['recording_sha256'])
            or plan['recording_sha256'] != manifest.get('recording_sha256')
            or not isinstance(plan.get('source_boundary_review_sha256'), str)
            or not _SHA.fullmatch(plan['source_boundary_review_sha256'])
            or not isinstance(plan.get('source_timeline_sha256'), str)
            or not _SHA.fullmatch(plan['source_timeline_sha256'])
            or not _number(plan.get('duration_seconds'))
            or abs(plan['duration_seconds'] - manifest.get('recording_duration_seconds', -999)) > .15):
        raise ValueError('Recording or provenance identity mismatch')
    audit = audit_activity_evidence(manifest, evidence_root)
    if not audit['ok']:
        raise ValueError('Evidence audit failed: ' + str(audit['issues'][:3]))
    tables = plan.get('tables')
    windows = plan.get('review_window_seek_associations')
    if (not isinstance(tables, list) or not 1 <= len(tables) <= 4
            or not isinstance(windows, list) or len(windows) > 10000
            or not isinstance(plan.get('skipped_review_windows'), list)
            or len(manifest['frames']) > max_images):
        raise ValueError('Unbounded or invalid review input')
    planned = {}
    for table in tables:
        if not isinstance(table, dict) or type(table.get('table_id')) is not int or not 1 <= table['table_id'] <= 4:
            raise ValueError('Invalid table')
        rows = table.get('requested_frames')
        if not isinstance(rows, list) or not rows or table.get('planned_count') != len(rows):
            raise ValueError('Invalid planned table count')
        for row in rows:
            if (not isinstance(row, dict) or not _number(row.get('requested_seek_seconds'))
                    or row.get('reason') != 'unverified_activity_neighborhood'):
                raise ValueError('Invalid boundary seek')
            key = (table['table_id'], row['requested_seek_seconds'])
            if key in planned:
                raise ValueError('Duplicate planned seek')
            planned[key] = row['reason']
    if (plan.get('planned_total_frames') != len(planned)
            or manifest.get('requested_count') != len(planned)):
        raise ValueError('Requested seek count mismatch')
    seen, frame_by_seek, unresolved_by_seek = set(), {}, {}
    for row in manifest['frames']:
        key = (row['table_id'], row['requested_seek_seconds'])
        if key not in planned or key in seen or row.get('seek_reason') != planned[key]:
            raise ValueError('Unexpected, duplicated or relabelled evidence frame')
        seen.add(key)
        frame_by_seek[key] = row
    for row in manifest['unresolved']:
        key = (row['table_id'], row['requested_seek_seconds'])
        if key not in planned or key in seen:
            raise ValueError('Unexpected or duplicated unresolved seek')
        seen.add(key)
        unresolved_by_seek[key] = row
    if seen != set(planned):
        raise ValueError('Unaccounted planned seeks')
    used, result_windows = set(), []
    for window in windows:
        if (not isinstance(window, dict) or type(window.get('review_window_index')) is not int
                or window['review_window_index'] < 0
                or type(window.get('table_id')) is not int
                or window.get('status') != 'unverified_review_only_not_hand_boundary'
                or not isinstance(window.get('candidate_interval_pts'), list)
                or len(window['candidate_interval_pts']) != 2
                or not all(_number(x) for x in window['candidate_interval_pts'])
                or not window['candidate_interval_pts'][0] < window['candidate_interval_pts'][1]
                or not isinstance(window.get('requested_seek_seconds'), list)):
            raise ValueError('Invalid review window association')
        start, end = window['candidate_interval_pts']
        frames = []
        for t in window['requested_seek_seconds']:
            key = (window['table_id'], t)
            if (not _number(t) or not start < t < end or key not in planned or key in used):
                raise ValueError('Unmatched or duplicated window seek')
            used.add(key)
            if key in unresolved_by_seek:
                frames.append({'requested_seek_seconds': t, 'status': 'no_decoded_frame',
                               'decoded_source_pts_seconds': None, 'image': None})
            else:
                row = frame_by_seek[key]
                if not _IMAGE.fullmatch(row['image']):
                    raise ValueError('Unsafe PNG name')
                frames.append({'requested_seek_seconds': t,
                               'decoded_source_pts_seconds': row['timestamp_seconds'],
                               'decoded_source_pts_ticks': row['source_pts_ticks'],
                               'seek_drift_seconds': row['seek_drift_seconds'],
                               'image': 'images/' + row['image'],
                               'sha256': row['sha256'],
                               'status': ('decoded_outside_candidate_interval_review_required'
                                          if not start <= row['timestamp_seconds'] <= end
                                          else 'unverified_visual_evidence')})
        result_windows.append({'review_window_index': window['review_window_index'],
                               'table_id': window['table_id'],
                               'candidate_interval_pts': [start, end],
                               'frames': frames,
                               'requires_manual_review': True,
                               'exact_boundary_known': False})
    if used != set(planned):
        raise ValueError('Orphan seek outside all review windows')
    return {'schema_version': 1, 'analysis_status': 'offline_boundary_contact_sheet_review_only',
            'recording_sha256': plan['recording_sha256'],
            'source_seek_plan_sha256': canonical_sha256(plan),
            'source_evidence_manifest_sha256': canonical_sha256(manifest),
            'source_boundary_review_sha256': plan['source_boundary_review_sha256'],
            'timestamp_semantics': 'requested_seeks_distinct_from_decoded_filtergraph_pts',
            'windows': result_windows, 'requested_count': len(planned),
            'resolved_count': len(frame_by_seek),
            'unresolved_count': len(unresolved_by_seek),
            'requires_manual_review': True, 'automatic_hand_boundaries_authorized': False,
            'automatic_clip_selection_authorized': False, 'ready_for_equity_or_ev': False,
            'strategic_error_established': False,
            'warning': ('Decoded PTS and images are review evidence, not exact hand '
                        'boundaries or validated cards, actions, equity or EV.')}


def _html(report):
    cards = []
    for window in report['windows']:
        start, end = window['candidate_interval_pts']
        imgs = []
        for frame in window['frames']:
            label = (f"Solicitado: {frame['requested_seek_seconds']:.3f}s · "
                     + (f"PTS decodificado: {frame['decoded_source_pts_seconds']:.3f}s"
                        if frame['decoded_source_pts_seconds'] is not None else 'sem quadro decodificado'))
            img = frame.get('image')
            image_tag = (f'<img loading="lazy" src="{escape(img, quote=True)}" '
                         f'alt="Quadro não confirmado">' if img else '<p>Sem imagem</p>')
            imgs.append(f'<figure>{image_tag}<figcaption>{escape(label)}<br>'
                        f'{escape(frame["status"])}</figcaption></figure>')
        cards.append(f'<section><h2>Mesa {window["table_id"]} · janela '
                     f'{window["review_window_index"]} ({start:.3f}–{end:.3f}s)</h2>'
                     f'<div class="frames">{"".join(imgs)}</div></section>')
    return ('<!doctype html><html lang="pt-BR"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>PLO — revisão de transições</title><style>'
            'body{font:16px system-ui;background:#151c27;color:#f4f4f4;margin:2rem}'
            'section{border:1px solid #687589;border-radius:12px;padding:1rem;margin:1rem 0}'
            '.frames{display:flex;flex-wrap:wrap;gap:1rem}figure{margin:0;max-width:360px}'
            'img{max-width:100%;height:auto}figcaption{font-size:.85rem;color:#d4dbe4}'
            '</style><h1>Revisão offline de possíveis transições</h1>'
            '<p>Quadros NÃO confirmam início/fim de mãos, cartas ou ações. '
            'Solicitação de seek ≠ PTS decodificado. Revisão humana obrigatória.</p>'
            + ''.join(cards) + '</html>')


def export_boundary_contact_sheet(plan_path, evidence_dir, output_dir, *, max_total_png_bytes=30_000_000):
    """Create a self-contained HTML/JSON/PNG packet, refusing existing outputs."""
    source = Path(evidence_dir)
    dest = Path(output_dir)
    if (source.is_symlink() or not source.is_dir() or dest.exists() or dest.is_symlink()
            or type(max_total_png_bytes) is not int or not 1 <= max_total_png_bytes <= 100_000_000):
        raise ValueError('Unsafe evidence/output directory or byte budget')
    plan_file = Path(plan_path)
    manifest_file = source / 'manifest.json'
    if (plan_file.is_symlink() or manifest_file.is_symlink()
            or not plan_file.is_file() or not manifest_file.is_file()):
        raise ValueError('Require regular JSON inputs')
    plan = json.loads(plan_file.read_text(encoding='utf-8'))
    manifest = json.loads(manifest_file.read_text(encoding='utf-8'))
    report = build_boundary_contact_sheet(plan, manifest, source)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='plo_boundary_sheet_', dir=dest.parent) as tmp:
        root = Path(tmp)
        copied, total = set(), 0
        for window in report['windows']:
            for frame in window['frames']:
                if not frame.get('image') or frame['image'] in copied:
                    continue
                copied.add(frame['image'])
                relative = frame['image'].removeprefix('images/')
                if not _IMAGE.fullmatch(relative):
                    raise ValueError('Unsafe image path')
                original = source / relative
                if original.is_symlink() or not original.is_file():
                    raise ValueError('Missing or symlink image')
                total += original.stat().st_size
                if total > max_total_png_bytes:
                    raise ValueError('PNG byte budget exceeded')
                target = root / frame['image']
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(original, target)
                if _sha_file(target) != frame['sha256']:
                    raise ValueError('Copied PNG hash mismatch')
        (root / 'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False,
                                                      allow_nan=False) + '\n', encoding='utf-8')
        (root / 'index.html').write_text(_html(report), encoding='utf-8')
        if dest.exists():
            raise FileExistsError('Output already exists')
        root.rename(dest)
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('boundary_seek_plan_json')
    p.add_argument('evidence_directory')
    p.add_argument('output_directory')
    args = p.parse_args()
    result = export_boundary_contact_sheet(args.boundary_seek_plan_json,
                                           args.evidence_directory, args.output_directory)
    print(json.dumps({'windows': len(result['windows']),
                      'resolved': result['resolved_count'],
                      'unresolved': result['unresolved_count']}))
