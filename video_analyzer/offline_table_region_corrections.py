"""Auditable offline corrections to FFmpeg table-region proposals.

Template: python offline_table_region_corrections.py template VIDEO PROPOSALS DRAFT
Review the original recording, then edit only DRAFT regions and reviewer_note.
Apply: python offline_table_region_corrections.py apply VIDEO PROPOSALS DRAFT OUT_DIR --confirm-reviewed
No OCR/EV authorization, live poker integration, or automatic approval.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import tempfile

import offline_table_region_proposals as base

STATUS = 'manual_offline_table_regions_unverified'
AUDIT_STATUS = 'offline_region_correction_audit_unverified'
FIELDS = {'table_id', 'x', 'y', 'width', 'height'}


def canonical(data):
    return json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + '\n'


def draft_template(video, proposals, target):
    video, proposals, target = map(Path, (video, proposals, target))
    base.safe_file(video)
    base.safe_file(proposals, max_size=2_000_000)
    base.require(not target.exists() and not target.is_symlink(), 'draft collision')
    p = base.read_json(proposals)
    base.require(type(p) is dict and p.get('source_video_sha256') == base.sha256(video)
                 and p.get('status') == base.STATUS and type(p.get('regions')) is list,
                 'untrusted proposal')
    draft = {'schema_version': 1, 'proposal_sha256': base.sha256(proposals),
             'source_video_sha256': p['source_video_sha256'],
             'reviewer_note': 'REPLACE WITH REASON FOR MANUAL CORRECTION',
             'regions': p['regions']}
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='plo_draft_', dir=target.parent) as d:
        tmp = Path(d) / 'draft.json'
        tmp.write_text(canonical(draft), encoding='utf-8')
        base.require(not target.exists() and not target.is_symlink(), 'draft collision')
        os.link(tmp, target)
    return draft


def validate_regions(regions, originals, width, height):
    base.require(type(regions) is list and len(regions) == len(originals),
                 'region count changed')
    original_ids = [r['table_id'] for r in originals]
    ids = []
    for r in regions:
        base.require(type(r) is dict and set(r) == FIELDS, 'invalid region keys')
        table = r['table_id']
        base.require(type(table) is str and table in original_ids and table not in ids,
                     'unknown/duplicate table ID')
        ids.append(table)
        x, y, w, h = (r[k] for k in ('x', 'y', 'width', 'height'))
        base.require(all(type(v) is int for v in (x, y, w, h)) and x >= 0 and y >= 0
                     and w >= 32 and h >= 32 and w % 2 == 0 and h % 2 == 0
                     and x + w <= width and y + h <= height,
                     'invalid/out-of-bounds region')
    base.require(ids == original_ids, 'table order changed')
    for i, a in enumerate(regions):
        for b in regions[i + 1:]:
            overlap = min(a['x'] + a['width'], b['x'] + b['width']) > max(a['x'], b['x']) and \
                      min(a['y'] + a['height'], b['y'] + b['height']) > max(a['y'], b['y'])
            base.require(not overlap, 'overlapping table regions')
    base.require(regions != originals, 'no corrections; use original confirmation command')


def apply(video, proposals, draft, output_dir, *, confirmed=False):
    base.require(confirmed is True, 'explicit human review confirmation required')
    video, proposals, draft, output_dir = map(Path, (video, proposals, draft, output_dir))
    base.safe_file(video)
    base.safe_file(draft, max_size=2_000_000)
    base.require(output_dir.is_dir() and not output_dir.is_symlink(), 'unsafe output directory')
    names = ('manual_layout.json', 'correction_audit.json', 'corrected_preview.png')
    base.require(all(not (output_dir / n).exists() and not (output_dir / n).is_symlink()
                     for n in names), 'output collision')
    # Recompute original evidence using the existing strict confirmation validator.
    with tempfile.TemporaryDirectory(prefix='plo_verify_proposal_') as d:
        original = base.confirm(video, proposals, Path(d) / 'verified.json', confirmed=True)
    p = base.read_json(proposals)
    correction = base.read_json(draft)
    base.require(type(correction) is dict and set(correction) ==
                 {'schema_version', 'proposal_sha256', 'source_video_sha256',
                  'reviewer_note', 'regions'} and type(correction['schema_version']) is int
                 and correction['schema_version'] == 1
                 and correction['proposal_sha256'] == base.sha256(proposals)
                 and correction['source_video_sha256'] == original['source_video_sha256'],
                 'correction provenance mismatch')
    note = correction['reviewer_note']
    base.require(type(note) is str and 12 <= len(note.strip()) <= 1000
                 and note != 'REPLACE WITH REASON FOR MANUAL CORRECTION',
                 'reviewer note required')
    width, height, duration = base.probe(video)
    regions = correction['regions']
    validate_regions(regions, original['regions'], width, height)
    changes = [{'table_id': new['table_id'], 'before': old, 'after': new}
               for old, new in zip(original['regions'], regions) if old != new]
    layout = {'schema_version': 1, 'status': STATUS,
              'source_video_sha256': original['source_video_sha256'], 'regions': regions}
    audit = {'schema_version': 1, 'status': AUDIT_STATUS,
             'source_video_sha256': original['source_video_sha256'],
             'proposal_sha256': base.sha256(proposals), 'draft_sha256': base.sha256(draft),
             'original_preview_sha256': p['preview_sha256'],
             'source_duration_seconds': duration,
             'human_confirmation_claimed': True, 'automatic_ocr_math_authorization': False,
             'reviewer_note': note.strip(), 'changes': changes,
             'warning': 'Human confirmation flag is not proof of actual review. Geometric correction is not a verified poker-table detection.'}
    published = []
    try:
        with tempfile.TemporaryDirectory(prefix='plo_corrected_', dir=output_dir) as d:
            d = Path(d)
            preview = d / 'corrected_preview.png'
            base.make_preview(video, duration * .5, regions, preview)
            audit['corrected_preview_sha256'] = base.sha256(preview)
            audit['manual_layout_sha256'] = __import__('hashlib').sha256(canonical(layout).encode()).hexdigest()
            (d / 'manual_layout.json').write_text(canonical(layout), encoding='utf-8')
            (d / 'correction_audit.json').write_text(canonical(audit), encoding='utf-8')
            base.require(base.sha256(video) == original['source_video_sha256']
                         and base.sha256(proposals) == audit['proposal_sha256']
                         and base.sha256(draft) == audit['draft_sha256'],
                         'source changed during correction')
            for name in names:
                dest = output_dir / name
                base.require(not dest.exists() and not dest.is_symlink(), 'output collision')
                os.link(d / name, dest)
                published.append(dest)
    except BaseException:
        for path in reversed(published):
            path.unlink(missing_ok=True)
        raise
    return audit


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    a = sub.add_parser('template')
    for name in ('video', 'proposals', 'draft'):
        a.add_argument(name)
    b = sub.add_parser('apply')
    for name in ('video', 'proposals', 'draft', 'output_dir'):
        b.add_argument(name)
    b.add_argument('--confirm-reviewed', action='store_true')
    args = parser.parse_args(argv)
    if args.command == 'template':
        result = draft_template(args.video, args.proposals, args.draft)
    else:
        result = apply(args.video, args.proposals, args.draft, args.output_dir,
                       confirmed=args.confirm_reviewed)
    print(json.dumps({'status': result.get('status', 'draft_unverified'),
                      'region_count': len(result.get('regions', [])),
                      'changes': len(result.get('changes', []))}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
