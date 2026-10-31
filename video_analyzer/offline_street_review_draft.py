"""Create an explicitly UNREVIEWED JSON draft from validated offline street evidence.

Usage: python offline_street_review_draft.py VIDEO OBSERVATIONS STREET_DIR OUTPUT_DIR
Fill every pending decision before passing manual_review.json to the human validator.
No live capture, automatic approval, equity or EV.
"""
import argparse
import json
import os
from pathlib import Path
import tempfile

import offline_ev_table_crop as media
import offline_street_evidence as street

NAME = 'manual_review_draft.json'


def export(video, observations, street_dir, output_dir):
    video, observations, street_dir, output_dir = map(Path, (video, observations, street_dir, output_dir))
    media.check(street_dir.is_dir() and not street_dir.is_symlink() and
                output_dir.is_dir() and not output_dir.is_symlink(), 'unsafe directories')
    media.check(len({p.resolve() for p in (video, observations, street_dir, output_dir)}) == 4,
                'paths must differ')
    target = output_dir / NAME
    media.check(not target.exists() and not target.is_symlink(), 'output collision')
    ledger_path = street_dir / street.REPORT
    stored = media.read_json(ledger_path)
    with tempfile.TemporaryDirectory(prefix='plo_draft_check_', dir=output_dir) as folder:
        expected, sources = street.validate(video, observations, folder)
    media.check(stored == expected, 'street report altered or mismatched')
    sources = tuple(sources) + ((ledger_path, media.digest(ledger_path)),)
    hands = []
    for hand in expected['hands']:
        events = [e for items in hand['streets'].values() for e in items]
        hands.append({'table_id': hand['table_id'], 'hand_id': hand['hand_id'],
                      'decisions': [{'event_index': i, 'decision': 'pending',
                                     'value': None, 'reason': ''} for i in range(len(events))]})
    result = {'schema_version': 1, 'status': 'manual_offline_street_review',
              'source_street_report_sha256': sources[-1][1],
              'reviewer_label': 'REPLACE_ME', 'hands': hands}
    with tempfile.TemporaryDirectory(prefix='plo_draft_write_', dir=output_dir) as folder:
        tmp = Path(folder) / NAME
        tmp.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n',
                       encoding='utf-8')
        media.check(all(media.digest(p) == sha for p, sha in sources), 'source changed')
        media.check(not target.exists() and not target.is_symlink(), 'output collision')
        os.link(tmp, target)
    return target


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ('video', 'observations', 'street_dir', 'output_dir'):
        parser.add_argument(arg)
    args = parser.parse_args(argv)
    print(export(args.video, args.observations, args.street_dir, args.output_dir))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
