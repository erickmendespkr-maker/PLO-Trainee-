"""Offline review gallery for independently audited action-timestamp PNGs.

Re-derives the requested frame plan from the original recording, navigation,
manual review and table rectangles. Verifies the audit manifest and PNG hashes.
A byte-matched nearby frame is *not* confirmation of any poker fact or strategy.
No OCR, equity, EV, hand reconstruction, or automatic clip selection occurs.
"""
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

from boundary_hand_draft import _read, _write
from hand_action_pts_evidence import (
    FALSE_FLAGS, MAX_FRAMES, PTS_TOLERANCE, _file, _sha, _validated_review,
    build_plan,
)

HEX = re.compile(r'[0-9a-f]{64}\Z')
TIMEBASE = re.compile(r'([1-9][0-9]*)/([1-9][0-9]*)\Z')
AUDIT_FIELDS = {
    'png_sha256', 'redecoded_png_sha256', 'pts_byte_matched',
    'decoded_pts_seconds', 'decoded_pts_ticks', 'decoded_pts_time_base',
    'requested_to_decoded_delta_seconds', 'within_requested_pts_tolerance',
    'status',
}
EXTRA_REPORT_FIELDS = {
    'source_review_sha256', 'source_regions_json_sha256',
    'timestamp_semantics', 'warning',
}


def _hex(value):
    return isinstance(value, str) and HEX.fullmatch(value) is not None


def _num(value):
    return type(value) in (int, float) and math.isfinite(value)


def _audit_frames(report, plan, evidence_dir):
    frames = report.get('frames')
    if not isinstance(frames, list) or len(frames) != len(plan['frames']):
        raise ValueError('Audit frame count differs from re-derived plan')
    root = Path(evidence_dir)
    if root.is_symlink() or not root.is_dir():
        raise ValueError('Evidence directory must be a regular directory')
    checked = []
    for item, expected in zip(frames, plan['frames']):
        if not isinstance(item, dict) or set(item) != set(expected) | AUDIT_FIELDS:
            raise ValueError('Unexpected audit frame fields')
        if any(type(item[k]) is not type(v) or item[k] != v for k, v in expected.items()):
            raise ValueError('Audit frame does not match planned source')
        if not _hex(item['png_sha256']) or not _hex(item['redecoded_png_sha256']):
            raise ValueError('Invalid PNG digest')
        if type(item['pts_byte_matched']) is not bool or type(item['within_requested_pts_tolerance']) is not bool:
            raise ValueError('Invalid PTS verification flags')
        matched = item['pts_byte_matched']
        pts, ticks, timebase = (item['decoded_pts_seconds'], item['decoded_pts_ticks'],
                                item['decoded_pts_time_base'])
        delta = item['requested_to_decoded_delta_seconds']
        if matched:
            m = TIMEBASE.fullmatch(timebase) if isinstance(timebase, str) else None
            if (not m or type(ticks) is not int or not _num(pts) or not _num(delta)
                    or pts < 0 or pts > plan['video']['duration_seconds'] + PTS_TOLERANCE
                    or item['png_sha256'] != item['redecoded_png_sha256']
                    or abs(ticks * int(m[1]) / int(m[2]) - pts) > 0.00001
                    or abs((pts - item['requested_seek_seconds']) - delta) > 0.00001):
                raise ValueError('Inconsistent decoded PTS')
        elif any(x is not None for x in (pts, ticks, timebase, delta)):
            raise ValueError('Unmatched frame must not claim decoded PTS')
        nearby = matched and abs(delta) <= PTS_TOLERANCE
        status = ('audited_near_requested_pts_not_content_verified' if nearby
                  else 'no_usable_nearby_audited_frame')
        if item['within_requested_pts_tolerance'] is not nearby or item['status'] != status:
            raise ValueError('Forged nearby-frame status')
        image = root / expected['filename']
        if (image.is_symlink() or not image.is_file()
                or not 100 < image.stat().st_size <= 20_000_000):
            raise ValueError('Missing, symlinked or invalid PNG')
        with image.open('rb') as stream:
            if stream.read(8) != bytes.fromhex('89504e470d0a1a0a'):
                raise ValueError('Not a PNG')
        if _sha(image) != item['png_sha256']:
            raise ValueError('PNG SHA-256 mismatch')
        checked.append(item)
    return checked


def build(video, navigation, navigation_sha, review, review_sha, report,
          evidence_dir, *, regions=None, regions_sha=None):
    """Recheck provenance and construct a no-math per-annotation review packet."""
    _validated_review(navigation, navigation_sha, review)
    if not _hex(review_sha) or (regions_sha is not None and not _hex(regions_sha)):
        raise ValueError('Invalid source hash')
    if not isinstance(report, dict) or not isinstance(report.get('counts'), dict):
        raise ValueError('Invalid action audit report')
    n = report['counts'].get('frames_planned')
    if type(n) is not int or not 0 <= n <= MAX_FRAMES:
        raise ValueError('Invalid frame budget in audit')
    plan = build_plan(video, navigation, navigation_sha, review,
                      max_frames=max(1, n), table_regions=regions)
    if (set(report) != set(plan) | EXTRA_REPORT_FIELDS
            or report['analysis_status'] != 'manual_action_pts_audit_no_content_validation'
            or report['source_review_sha256'] != review_sha
            or report['source_regions_json_sha256'] != regions_sha
            or report['timestamp_semantics'] != 'ffmpeg_filtergraph_pts_not_wall_clock'
            or not isinstance(report['warning'], str)):
        raise ValueError('Audit provenance or schema mismatch')
    for key, expected in plan.items():
        if key not in ('analysis_status', 'frames', 'counts') and report[key] != expected:
            raise ValueError('Audit plan differs from source: ' + key)
    frames = _audit_frames(report, plan, evidence_dir)
    expected_counts = {**plan['counts'],
                       'pts_byte_matched': sum(f['pts_byte_matched'] for f in frames),
                       'near_requested_pts': sum(f['within_requested_pts_tolerance'] for f in frames)}
    if report['counts'] != expected_counts:
        raise ValueError('Audit counts inconsistent')
    associations = {(a['entry_id'], a['kind'], a['item']): a['frame_id']
                    for a in plan['associations']}
    if len(associations) != len(plan['associations']):
        raise ValueError('Duplicate action associations')
    skipped = {(s['entry_id'], s['kind'], s['item']): s['reason']
               for s in plan['skipped']}
    rows = []
    for entry in review['entries']:
        items = []
        for name, field in entry['fields'].items():
            items.append(('field', name, field, field['source_pts_seconds']))
        for index, action in enumerate(entry['actions']):
            items.append(('action', index, action, action['timestamp_seconds']))
        links = []
        for kind, item, annotation, pts in items:
            key = (entry['entry_id'], kind, item)
            source = annotation['source_kind']
            confirmed = annotation['human_confirmed']
            if source == 'unknown':
                status = 'unknown'
            elif source == 'hypothesis':
                status = 'hypothesis_not_evidence'
            elif not confirmed:
                status = 'manual_claim_not_confirmed'
            elif key in skipped:
                status = skipped[key]
            elif key not in associations:
                raise ValueError('Confirmed annotation omitted from frame plan')
            else:
                frame = frames[associations[key]]
                status = ('nearby_audited_frame_not_content_verified'
                          if frame['within_requested_pts_tolerance']
                          else 'no_usable_nearby_audited_frame')
            frame = (frames[associations[key]] if key in associations else None)
            links.append({'kind': kind, 'item': item, 'value': annotation.get('value') if kind == 'field'
                          else {'actor': annotation['actor'], 'action': annotation['action'],
                                'amount': annotation['amount']},
                          'source_kind': source, 'human_confirmed': confirmed,
                          'confidence': annotation['confidence'],
                          'requested_pts_seconds': pts, 'status': status,
                          'frame': ({'filename': frame['filename'], 'frame_id': frame['frame_id'],
                                     'decoded_pts_seconds': frame['decoded_pts_seconds'],
                                     'png_sha256': frame['png_sha256']}
                                    if frame and frame['within_requested_pts_tolerance'] else None)})
        rows.append({'entry_id': entry['entry_id'], 'table_id': entry['table_id'],
                     'start_human_seconds': entry['start_human_seconds'],
                     'end_human_seconds': entry['end_human_seconds'],
                     'contains_unresolved_interior_candidates': entry['contains_unresolved_interior_candidates'],
                     'links': links})
    return {'schema_version': 1,
            'analysis_status': 'manual_action_still_gallery_unverified_no_math',
            'recording_sha256': plan['recording_sha256'],
            'source_navigation_sha256': navigation_sha,
            'source_review_sha256': review_sha,
            'source_action_audit_sha256': None,  # filled by export from source bytes
            'entries': rows,
            'counts': {'entries': len(rows), 'annotations': sum(len(x['links']) for x in rows),
                       'nearby_audited_links': sum(l['frame'] is not None for x in rows for l in x['links']),
                       'frames_hashed': len(frames)},
            'warning': 'Images verify bytes and timing only; no card/action/hand or strategic claim is confirmed.',
            'requires_manual_review': True, **{key: False for key in FALSE_FLAGS}}


def _gallery_html(packet, evidence_dir, output_dir):
    # All text and attribute values are escaped, including reviewer-provided data.
    relative = os.path.relpath(Path(evidence_dir).resolve(), Path(output_dir).resolve())
    parts = ['<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">',
             '<meta name="viewport" content="width=device-width,initial-scale=1">',
             '<title>PLO Trainee — revisão visual offline</title>',
             '<style>body{font:16px system-ui,sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem}',
             'article{border:1px solid #bbb;border-radius:8px;padding:1rem;margin:1rem 0}',
             'img{max-width:100%;height:auto;border:1px solid #888}small{color:#555}',
             'code{overflow-wrap:anywhere} .warn{background:#fff0cc;padding:1rem}</style></head><body>',
             '<h1>PLO Trainee — revisão visual offline</h1>',
             '<p class="warn">Quadros auditados não confirmam cartas, ações, limites de mãos, equity ou EV. '
             'Revisão humana obrigatória. Nenhuma análise de jogo ao vivo.</p>']
    for entry in packet['entries']:
        parts.append('<h2>' + html.escape(entry['entry_id']) + '</h2>')
        if entry['contains_unresolved_interior_candidates']:
            parts.append('<p class="warn">Há transições internas ainda não resolvidas.</p>')
        for link in entry['links']:
            title = f"{link['kind']} {link['item']} — {link['status']}"
            parts.append('<article><strong>' + html.escape(title) + '</strong>')
            parts.append('<p>Valor: <code>' + html.escape(json.dumps(link['value'], ensure_ascii=False)) +
                         '</code><br>Confiança informada: ' + html.escape(str(link['confidence'])) +
                         ' | PTS solicitado: ' + html.escape(str(link['requested_pts_seconds'])) + '</p>')
            if link['frame']:
                frame = link['frame']
                src = Path(relative) / frame['filename']
                parts.append('<img loading="lazy" alt="Quadro para revisão, conteúdo não verificado" src="' +
                             html.escape(src.as_posix(), quote=True) + '">')
                parts.append('<p><small>PTS decodificado: ' +
                             html.escape(str(frame['decoded_pts_seconds'])) +
                             ' | SHA-256: <code>' + html.escape(frame['png_sha256']) + '</code></small></p>')
            parts.append('</article>')
    parts.append('</body></html>')
    return '\n'.join(parts) + '\n'


def export(video_path, navigation_path, review_path, evidence_dir, output_dir,
           *, regions_json=None):
    sources = [_file(p) for p in (video_path, navigation_path, review_path)]
    root = Path(evidence_dir)
    manifest = _file(root / 'action_pts_evidence.json')
    sources.append(manifest)
    if regions_json is not None:
        sources.append(_file(regions_json))
    if len({p.resolve() for p in sources}) != len(sources):
        raise ValueError('Input paths must be distinct')
    output = Path(output_dir)
    if (output.exists() or output.is_symlink() or root.is_symlink() or not root.is_dir()
            or output.resolve().is_relative_to(root.resolve())
            or any(p.resolve().is_relative_to(output.resolve()) for p in sources)):
        raise ValueError('Output must be new and outside sources')
    digests = [_sha(p) for p in sources]
    navigation, nav_sha = _read(sources[1])
    review, review_sha = _read(sources[2])
    report, report_sha = _read(manifest)
    regions = _read(sources[4])[0] if regions_json is not None else None
    result = build(sources[0], navigation, nav_sha, review, review_sha, report,
                   root, regions=regions,
                   regions_sha=digests[4] if regions_json is not None else None)
    result['source_action_audit_sha256'] = report_sha
    # Check sources once more after all local evidence has been inspected.
    if any(_sha(p) != digest for p, digest in zip(sources, digests)):
        raise ValueError('Source changed during review gallery generation')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.plo_action_gallery_', dir=output.parent) as temp:
        stage = Path(temp)
        _write(stage / 'review_gallery.json', result)
        (stage / 'review_gallery.html').write_text(_gallery_html(result, root, output), encoding='utf-8')
        output.mkdir(exist_ok=False)
        try:
            for item in stage.iterdir():
                os.replace(item, output / item.name)
        except BaseException:
            shutil.rmtree(output)
            raise
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('video')
    parser.add_argument('navigation')
    parser.add_argument('review')
    parser.add_argument('action_evidence_dir')
    parser.add_argument('output_dir')
    parser.add_argument('--regions-json')
    args = parser.parse_args(argv)
    result = export(args.video, args.navigation, args.review, args.action_evidence_dir,
                    args.output_dir, regions_json=args.regions_json)
    print(json.dumps(result['counts'], sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
