"""Attach audited human still-verdicts to unverified PLO hand annotations.

This is an offline evidence index, NOT confirmation of reconstructed hands,
OCR correctness, opponent ranges, equity, EV, or strategic mistakes.
"""
import argparse
import json
from pathlib import Path

from boundary_hand_draft import _read, _write
from hand_action_pts_evidence import FALSE_FLAGS, _file, _sha
from hand_action_visual_verdicts import build_template, validate, verified_gallery


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':'), allow_nan=False)


def build(review, gallery, gallery_sha, verdicts, verdicts_sha):
    """Revalidate final verdicts against a rebuilt gallery; retain uncertainty."""
    template = build_template(gallery, gallery_sha)
    if not isinstance(verdicts, dict) or not isinstance(verdicts.get('rows'), list):
        raise ValueError('Finalized visual verdicts required')
    edited = {**template, 'rows': verdicts['rows']}
    expected = validate(gallery, gallery_sha, edited)
    if _canonical(expected) != _canonical(verdicts):
        raise ValueError('Visual verdicts are not an authentic finalized report')
    if (not isinstance(review, dict) or review.get('analysis_status') !=
            'manual_hand_history_review_unverified_no_math'
            or review.get('recording_sha256') != gallery['recording_sha256']
            or not isinstance(review.get('entries'), list)):
        raise ValueError('Unverified manual hand history required')
    visual = {(r['entry_id'], r['kind'], r['item']): r for r in verdicts['rows']}
    entries, used = [], set()
    for entry in gallery['entries']:
        matching = next((e for e in review['entries'] if e['entry_id'] == entry['entry_id']), None)
        if matching is None or matching['table_id'] != entry['table_id']:
            raise ValueError('Gallery entry does not match hand history')
        annotations = []
        for link in entry['links']:
            key = (entry['entry_id'], link['kind'], link['item'])
            if key not in visual or key in used:
                raise ValueError('Missing or duplicate visual verdict')
            used.add(key)
            v = visual[key]
            annotations.append({
                'kind': link['kind'], 'item': link['item'],
                'claimed_value': link['value'],
                'source_kind': link['source_kind'],
                'human_confirmed_original_claim': link['human_confirmed'],
                'source_confidence': link['confidence'],
                'requested_pts_seconds': link['requested_pts_seconds'],
                'still_sha256': v['frame_sha256'],
                'visual_verdict': v['verdict'],
                'visual_confidence_subjective': v['visual_confidence'],
                'visual_reviewer': v['reviewer'],
                'visual_review_notes': v['notes'],
                'evidence_status': ('human_still_review_only_not_hand_verified'
                                    if v['verdict'] == 'confirmed_visual'
                                    else 'not_visually_confirmed'),
                'ready_for_equity_or_ev': False,
            })
        entries.append({
            'entry_id': entry['entry_id'], 'table_id': entry['table_id'],
            'start_human_seconds': entry['start_human_seconds'],
            'end_human_seconds': entry['end_human_seconds'],
            'contains_unresolved_interior_candidates': entry['contains_unresolved_interior_candidates'],
            'hand_reconstruction_verified': False,
            'annotations': annotations,
            'ready_for_equity_or_ev': False,
        })
    if len(used) != len(visual) or len(entries) != len(review['entries']):
        raise ValueError('Unmatched visual or hand history entry')
    return {
        'schema_version': 1,
        'analysis_status': 'visual_verdicts_linked_to_unverified_hand_history_no_math',
        'recording_sha256': gallery['recording_sha256'],
        'source_navigation_sha256': gallery['source_navigation_sha256'],
        'source_review_sha256': gallery['source_review_sha256'],
        'source_gallery_sha256': gallery_sha,
        'source_visual_verdicts_sha256': verdicts_sha,
        'entries': entries,
        'counts': {'spans': len(entries), 'annotations': len(used),
                   **{name: verdicts['counts'][name] for name in (
                       'pending', 'confirmed_visual', 'rejected_visual',
                       'uncertain', 'unreviewable')}},
        'warning': ('A human verdict describes one audited still only. No complete hand, '
                    'card/action correctness, opponent range, equity, EV, or mistake is verified.'),
        'requires_manual_review': True,
        **{flag: False for flag in FALSE_FLAGS},
    }


def export(video, navigation, review, evidence_dir, gallery_dir,
           visual_verdicts_path, output_path, *, regions_json=None):
    """Rebuild all evidence before writing a new, immutable output JSON."""
    sources = [video, navigation, review,
               Path(evidence_dir) / 'action_pts_evidence.json',
               Path(gallery_dir) / 'review_gallery.json', visual_verdicts_path]
    if regions_json is not None:
        sources.append(regions_json)
    sources = [_file(path) for path in sources]
    if len({p.resolve() for p in sources}) != len(sources):
        raise ValueError('Source paths must be distinct')
    output = Path(output_path)
    if (output.exists() or output.is_symlink()
            or any(output.resolve().is_relative_to(Path(root).resolve())
                   for root in (evidence_dir, gallery_dir))
            or output.resolve() in {p.resolve() for p in sources}):
        raise ValueError('Output must be new and outside evidence sources')
    hashes = [_sha(path) for path in sources]
    gallery, gallery_sha = verified_gallery(video, navigation, review,
                                           evidence_dir, gallery_dir, regions_json)
    reviewed, _ = _read(review)
    verdicts, verdicts_sha = _read(visual_verdicts_path)
    result = build(reviewed, gallery, gallery_sha, verdicts, verdicts_sha)
    if any(_sha(p) != h for p, h in zip(sources, hashes)):
        raise ValueError('Source changed during verification')
    _write(output, result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('video')
    parser.add_argument('navigation')
    parser.add_argument('review')
    parser.add_argument('evidence_dir')
    parser.add_argument('gallery_dir')
    parser.add_argument('visual_verdicts')
    parser.add_argument('output')
    parser.add_argument('--regions-json')
    args = parser.parse_args(argv)
    result = export(args.video, args.navigation, args.review, args.evidence_dir,
                    args.gallery_dir, args.visual_verdicts, args.output,
                    regions_json=args.regions_json)
    print(json.dumps({'analysis_status': result['analysis_status'],
                      'counts': result['counts']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
