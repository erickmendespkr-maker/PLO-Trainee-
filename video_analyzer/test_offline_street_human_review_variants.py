"""PLO6 and four-table synthetic human-review integration checks."""
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import offline_ev_table_crop as media
import offline_street_evidence as street
import offline_street_human_review as review


class ReviewVariantsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='plo6_review_')
        cls.root = Path(cls.temp.name)
        cls.video = cls.root / 'four_tables.mp4'
        subprocess.run(['ffmpeg', '-nostdin', '-loglevel', 'error', '-y',
                        '-f', 'lavfi', '-i', 'color=c=blue:s=160x120:r=5',
                        '-t', '3', '-c:v', 'mpeg4', str(cls.video)],
                       capture_output=True, check=True, timeout=30)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_four_tables_plo6_confirmed_not_math_authorized(self):
        with tempfile.TemporaryDirectory(prefix='plo6_case_') as folder:
            root = Path(folder)
            source = {'schema_version': 1,
                      'status': 'offline_unverified_street_observations',
                      'source_video_sha256': media.digest(self.video), 'variant': 'PLO6',
                      'hands': []}
            for i in range(1, 5):
                source['hands'].append({'table_id': f'T{i}', 'hand_id': f'H{i}',
                    'start_seconds': 0.1, 'end_seconds': 2.9, 'events': [
                        {'timestamp_seconds': 0.5, 'street': 'preflop',
                         'kind': 'hero_cards', 'value': ['AS', 'KH', 'QD', 'JC', 'TS', '9H'],
                         'origin': 'ocr_proposal', 'confidence': 0.4}]})
            obs = root / 'obs.json'
            obs.write_text(json.dumps(source))
            street_dir = root / 'streets'; street_dir.mkdir()
            street.export(self.video, obs, street_dir)
            human = {'schema_version': 1, 'status': 'manual_offline_street_review',
                     'source_street_report_sha256': media.digest(street_dir / street.REPORT),
                     'reviewer_label': 'test_operator', 'hands': []}
            for i in range(1, 5):
                human['hands'].append({'table_id': f'T{i}', 'hand_id': f'H{i}',
                    'decisions': [{'event_index': 0, 'decision': 'confirm',
                                   'value': None, 'reason': ''}]})
            review_path = root / 'human.json'
            review_path.write_text(json.dumps(human))
            out = root / 'out'; out.mkdir()
            result = review.export(self.video, obs, street_dir, review_path, out)
            self.assertEqual(result['variant'], 'PLO6')
            self.assertEqual(len(result['hands']), 4)
            self.assertTrue(all(not h['automatic_math_authorization'] for h in result['hands']))
            self.assertEqual(result['source_video_sha256'], media.digest(self.video))


if __name__ == '__main__':
    unittest.main()
