"""Build a verified offline attachment index for human-reviewed clip galleries.

No OCR, no automatic hand identification, no poker-site connection, no action grade.
Requires explicitly named H001.ack.json and H001.ev.json beside each clip.
The existing gallery validator checks identity, hashes, cards and uncertainty flags.
Usage: python offline_gallery_attachment_index.py CLIP_DIR NEW_ATTACHMENTS.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import offline_reviewed_clip_gallery as gallery


def build(root):
    root = Path(root)
    # Validates manifest, all MP4 hashes, sidecars and reviewer declarations.
    snapshot = gallery.build(root)
    mapping = {}
    for clip in snapshot['clips']:
        hand = clip['hand_id']
        report_name, sensitivity_name = hand + '.ack.json', hand + '.ev.json'
        report = root / report_name
        sensitivity = root / sensitivity_name
        # Reject half-configured pairs; absence of both is an explicit no-analysis.
        gallery.require(report.exists() == sensitivity.exists(),
                        f'incomplete analysis pair for {hand}')
        if not report.exists():
            continue
        gallery.local_file(root, report_name, '.json', 2_000_000)
        gallery.local_file(root, sensitivity_name, '.json', 4_000_000)
        # Fail closed if even one analysis is not bound to this exact clip/video.
        gallery.analysis(root, hand, clip['clip_sha256'],
                         snapshot['source_video_sha256_claim'],
                         {'acknowledged_report': report_name,
                          'sensitivity': sensitivity_name})
        mapping[hand] = {'acknowledged_report': report_name,
                         'sensitivity': sensitivity_name}
    # Manifest and clip hashes must remain stable throughout the scan.
    again = gallery.build(root)
    gallery.require(snapshot['source_manifest_sha256'] ==
                    again['source_manifest_sha256'] and
                    [(x['hand_id'], x['clip_sha256'], x['sidecar_sha256'])
                     for x in snapshot['clips']] ==
                    [(x['hand_id'], x['clip_sha256'], x['sidecar_sha256'])
                     for x in again['clips']], 'clip evidence changed during scan')
    return {'schema_version': 1, 'analyses': mapping}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('clip_dir')
    parser.add_argument('new_attachments_json')
    args = parser.parse_args(argv)
    root = Path(args.clip_dir)
    dest = Path(args.new_attachments_json)
    gallery.require(root.is_dir() and not root.is_symlink() and
                    dest.parent.resolve() == root.resolve() and
                    dest.suffix == '.json' and not dest.exists() and
                    not dest.is_symlink() and dest.name not in
                    {'manifest.json'}, 'output must be a new JSON in clip directory')
    result = build(root)
    # Confirm the index is consumable by the gallery before writing.
    with dest.open('x', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False, allow_nan=False)
        f.write('\n')
    try:
        gallery.build(root, dest.name)
    except Exception:
        dest.unlink()
        raise
    print(json.dumps({'index': str(dest),
                      'analyses_attached': len(result['analyses']),
                      'action_graded': False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
