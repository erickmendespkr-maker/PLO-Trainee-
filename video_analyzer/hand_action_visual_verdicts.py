"""Offline, human-only visual verdicts bound to an audited action gallery.

Verdicts describe a person's inspection of a still, not a reconstructed hand.
No automatic equity/EV/clip authority is granted, even for confirmed visuals.
"""
import argparse
import json
import math
from pathlib import Path

from boundary_hand_draft import _read, _write
from hand_action_pts_evidence import _file, _sha, FALSE_FLAGS
from hand_action_review_gallery import build as rebuild_gallery

VERDICTS = ('pending', 'confirmed_visual', 'rejected_visual', 'uncertain', 'unreviewable')
EDITABLE = frozenset(('verdict', 'reviewer', 'notes', 'visual_confidence'))
MAX_LINKS = 3000


def build_template(gallery, gallery_sha):
    """Create a strictly bound form; only audited, manual claims can be reviewed."""
    if (not isinstance(gallery, dict) or gallery.get('schema_version') != 1
            or gallery.get('analysis_status') != 'manual_action_still_gallery_unverified_no_math'
            or gallery.get('requires_manual_review') is not True
            or any(gallery.get(flag) is not False for flag in FALSE_FLAGS)
            or not isinstance(gallery_sha, str) or len(gallery_sha) != 64
            or any(c not in '0123456789abcdef' for c in gallery_sha)):
        raise ValueError('Invalid gallery provenance or authority')
    entries = gallery.get('entries')
    if not isinstance(entries, list) or len(entries) > 2048:
        raise ValueError('Invalid gallery entries')
    rows, keys = [], set()
    for entry in entries:
        if (not isinstance(entry, dict) or not isinstance(entry.get('entry_id'), str)
                or type(entry.get('table_id')) is not int
                or not 1 <= entry['table_id'] <= 4
                or not isinstance(entry.get('links'), list)):
            raise ValueError('Invalid gallery entry')
        for link in entry['links']:
            if not isinstance(link, dict):
                raise ValueError('Invalid gallery link')
            kind, item = link.get('kind'), link.get('item')
            if kind not in ('field', 'action') or (kind == 'field' and not isinstance(item, str)) or (kind == 'action' and (type(item) is not int or item < 0)):
                raise ValueError('Invalid annotation identifier')
            key = (entry['entry_id'], kind, item)
            if key in keys:
                raise ValueError('Duplicate gallery annotation')
            keys.add(key)
            frame = link.get('frame')
            eligible = (link.get('status') == 'nearby_audited_frame_not_content_verified'
                        and link.get('source_kind') == 'manual_video_review'
                        and link.get('human_confirmed') is True
                        and isinstance(frame, dict) and isinstance(frame.get('png_sha256'), str)
                        and len(frame['png_sha256']) == 64)
            rows.append({'entry_id': entry['entry_id'], 'table_id': entry['table_id'],
                         'kind': kind, 'item': item, 'source_status': link.get('status'),
                         'frame_sha256': frame['png_sha256'] if eligible else None,
                         'requested_pts_seconds': link.get('requested_pts_seconds'),
                         'verdict': 'pending' if eligible else 'unreviewable',
                         'reviewer': '', 'notes': '', 'visual_confidence': None})
            if len(rows) > MAX_LINKS:
                raise ValueError('Too many annotations')
    return {'schema_version': 1,
            'analysis_status': 'manual_visual_verdict_form_no_math',
            'source_gallery_sha256': gallery_sha,
            'recording_sha256': gallery['recording_sha256'],
            'rows': rows, 'requires_manual_review': True,
            **{flag: False for flag in FALSE_FLAGS}}


def validate(gallery, gallery_sha, edited):
    """Reject forged identities, status upgrades and reviews without an audited still."""
    template = build_template(gallery, gallery_sha)
    if not isinstance(edited, dict) or set(edited) != set(template):
        raise ValueError('Unexpected verdict document fields')
    for key in template:
        if key != 'rows' and (type(edited[key]) is not type(template[key])
                              or edited[key] != template[key]):
            raise ValueError('Protected verdict document field changed: ' + key)
    if not isinstance(edited['rows'], list) or len(edited['rows']) != len(template['rows']):
        raise ValueError('Verdict row count changed')
    counts = {v: 0 for v in VERDICTS}
    for row, expected in zip(edited['rows'], template['rows']):
        if not isinstance(row, dict) or set(row) != set(expected):
            raise ValueError('Invalid verdict row')
        for key in expected:
            if key in EDITABLE:
                continue
            # JSON.stringify in offline browsers serializes 2.0 as 2. These
            # represent the same PTS; only this numeric timestamp field may
            # change int/float representation. Never coerce booleans or IDs.
            if (key == 'requested_pts_seconds' and type(row[key]) in (int, float)
                    and type(expected[key]) in (int, float)):
                equal = math.isfinite(row[key]) and row[key] == expected[key]
            else:
                equal = type(row[key]) is type(expected[key]) and row[key] == expected[key]
            if not equal:
                raise ValueError('Protected visual reference changed: ' + key)
        verdict = row['verdict']
        if type(verdict) is not str or verdict not in VERDICTS:
            raise ValueError('Unknown visual verdict')
        if expected['verdict'] == 'unreviewable' and verdict != 'unreviewable':
            raise ValueError('Cannot review missing or unaudited visual evidence')
        if expected['verdict'] == 'pending' and verdict == 'unreviewable':
            raise ValueError('Cannot erase an eligible visual review task')
        reviewer, notes, confidence = row['reviewer'], row['notes'], row['visual_confidence']
        if type(reviewer) is not str or len(reviewer) > 80 or type(notes) is not str or len(notes) > 1000:
            raise ValueError('Invalid reviewer or notes')
        if verdict in ('pending', 'unreviewable'):
            if reviewer or notes or confidence is not None:
                raise ValueError('Unreviewed rows must not contain a verdict claim')
        else:
            if (not reviewer.strip() or len(notes.strip()) < 8
                    or type(confidence) not in (int, float)
                    or not math.isfinite(confidence) or not 0 <= confidence <= 1):
                raise ValueError('Human reviewer, rationale and finite confidence required')
        counts[verdict] += 1
    return {'schema_version': 1,
            'analysis_status': 'manual_visual_verdicts_unverified_hand_no_math',
            'source_gallery_sha256': gallery_sha,
            'recording_sha256': template['recording_sha256'],
            'rows': edited['rows'], 'counts': counts,
            'warning': ('A human visual verdict does not prove complete hand reconstruction, '
                        'opponent ranges, equity, EV or strategic mistakes.'),
            'requires_manual_review': True,
            **{flag: False for flag in FALSE_FLAGS}}


def verified_gallery(video, navigation, review, evidence_dir, gallery_dir, regions_json=None):
    """Rebuild and compare the gallery using original inputs and PNG hashes."""
    video = _file(video)
    navigation = _file(navigation)
    review = _file(review)
    evidence_dir = Path(evidence_dir)
    gallery_dir = Path(gallery_dir)
    if evidence_dir.is_symlink() or gallery_dir.is_symlink():
        raise ValueError('Unsafe evidence or gallery directory')
    audit_path = _file(evidence_dir / 'action_pts_evidence.json')
    gallery_path = _file(gallery_dir / 'review_gallery.json')
    regions_path = _file(regions_json) if regions_json is not None else None
    sources = [video, navigation, review, audit_path, gallery_path]
    if regions_path is not None:
        sources.append(regions_path)
    if len({p.resolve() for p in sources}) != len(sources):
        raise ValueError('Source paths must be distinct')
    hashes = [_sha(p) for p in sources]
    nav, nav_sha = _read(navigation)
    reviewed, review_sha = _read(review)
    audit, audit_sha = _read(audit_path)
    gallery, gallery_sha = _read(gallery_path)
    regions = _read(regions_path)[0] if regions_path is not None else None
    expected = rebuild_gallery(video, nav, nav_sha, reviewed, review_sha, audit,
                               evidence_dir, regions=regions,
                               regions_sha=hashes[5] if regions_path is not None else None)
    expected['source_action_audit_sha256'] = audit_sha
    if gallery != expected or any(_sha(p) != h for p, h in zip(sources, hashes)):
        raise ValueError('Gallery is stale or source evidence changed')
    return gallery, gallery_sha


def export(mode, video, navigation, review, evidence_dir, gallery_dir,
           edited_or_output, output=None, *, regions_json=None):
    gallery, digest = verified_gallery(video, navigation, review, evidence_dir,
                                      gallery_dir, regions_json)
    if mode == 'template':
        if output is not None:
            raise ValueError('Template takes one output')
        result, destination = build_template(gallery, digest), edited_or_output
    elif mode == 'finalize':
        if output is None:
            raise ValueError('Finalization needs edited input and output')
        edited, _ = _read(edited_or_output)
        result, destination = validate(gallery, digest, edited), output
    else:
        raise ValueError('Unknown export mode')
    destination = Path(destination)
    source_paths = [video, navigation, review, Path(evidence_dir) / 'action_pts_evidence.json',
                    Path(gallery_dir) / 'review_gallery.json']
    if regions_json is not None:
        source_paths.append(regions_json)
    if mode == 'finalize':
        source_paths.append(edited_or_output)
    if destination.resolve() in {Path(p).resolve() for p in source_paths}:
        raise ValueError('Cannot overwrite an input')
    _write(destination, result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('template', 'finalize'))
    parser.add_argument('video')
    parser.add_argument('navigation')
    parser.add_argument('review')
    parser.add_argument('evidence_dir')
    parser.add_argument('gallery_dir')
    parser.add_argument('edited_or_output')
    parser.add_argument('output', nargs='?')
    parser.add_argument('--regions-json')
    args = parser.parse_args(argv)
    result = export(args.mode, args.video, args.navigation, args.review,
                    args.evidence_dir, args.gallery_dir, args.edited_or_output,
                    args.output, regions_json=args.regions_json)
    print(json.dumps({'analysis_status': result['analysis_status'],
                      'rows': len(result['rows'])}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
