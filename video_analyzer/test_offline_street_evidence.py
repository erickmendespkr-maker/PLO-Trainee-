"""Synthetic-only offline street evidence contract tests."""
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

import offline_ev_table_crop as media
import offline_street_evidence as mod


class StreetEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = tempfile.TemporaryDirectory(prefix='plo_street_fixture_')
        cls.root = Path(cls.fixture.name)
        cls.video = cls.root / 'sample.mp4'
        subprocess.run(['ffmpeg', '-nostdin', '-loglevel', 'error', '-y', '-f', 'lavfi',
                        '-i', 'testsrc2=size=160x120:rate=10', '-t', '4', '-an',
                        '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p',
                        str(cls.video)], capture_output=True, check=True, timeout=30)
        cls.source = {'schema_version': 1,
                      'status': 'offline_unverified_street_observations',
                      'source_video_sha256': media.digest(cls.video), 'variant': 'PLO5',
                      'hands': [{'table_id': 'T1', 'hand_id': 'H1', 'start_seconds': 0.2,
                                 'end_seconds': 3.8, 'events': [
                                     {'timestamp_seconds': .4, 'street': 'preflop',
                                      'kind': 'hero_cards',
                                      'value': ['AS', 'KH', 'QD', 'JC', 'TS'],
                                      'origin': 'ocr_proposal', 'confidence': .55},
                                     {'timestamp_seconds': 1.0, 'street': 'flop',
                                      'kind': 'board', 'value': ['2C', '3D', '4H'],
                                      'origin': 'manual_claim', 'confidence': 1.0},
                                     {'timestamp_seconds': 1.5, 'street': 'flop',
                                      'kind': 'action', 'value': 'check',
                                      'origin': 'ocr_proposal', 'confidence': .7},
                                     {'timestamp_seconds': 2.0, 'street': 'turn',
                                      'kind': 'board', 'value': ['2C', '3D', '4H', '5S'],
                                      'origin': 'ocr_proposal', 'confidence': .8}]}]}

    @classmethod
    def tearDownClass(cls):
        cls.fixture.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='plo_street_test_')
        self.root_out = Path(self.tmp.name)
        self.out = self.root_out / 'out'
        self.out.mkdir()
        self.observations = self.root_out / 'observations.json'
        self.write(self.source)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, obj):
        self.observations.write_text(json.dumps(obj, ensure_ascii=False) + '\n', encoding='utf-8')

    def changed(self, fn):
        obj = copy.deepcopy(self.source)
        fn(obj)
        self.write(obj)

    def test_export_json_and_html(self):
        result = mod.export(self.video, self.observations, self.out)
        self.assertEqual(result['table_count'], 1)
        self.assertEqual(result['hand_count'], 1)
        self.assertFalse(result['automatic_ocr_math_authorization'])
        self.assertFalse(result['confidence_calibrated'])
        self.assertEqual(result['hands'][0]['event_count'], 4)
        self.assertEqual(result['hands'][0]['review_flags'], [])
        self.assertEqual(set(x.name for x in self.out.iterdir()), {mod.REPORT, mod.PAGE})
        page = (self.out / mod.PAGE).read_text()
        self.assertIn('Evidências por street', page)
        self.assertNotIn('<script', page)
        self.assertEqual(json.loads((self.out / mod.REPORT).read_text())['source_observations_sha256'],
                         media.digest(self.observations))

    def test_html_escaping(self):
        self.changed(lambda x: x['hands'][0]['events'][2].update(value='<img src=x onerror=alert(1)>'))
        mod.export(self.video, self.observations, self.out)
        page = (self.out / mod.PAGE).read_text()
        self.assertIn('&lt;img', page)
        self.assertNotIn('<img', page)

    def test_plo6_six_cards(self):
        def change(x):
            x['variant'] = 'PLO6'
            x['hands'][0]['events'][0]['value'].append('9H')
        self.changed(change)
        self.assertEqual(mod.export(self.video, self.observations, self.out)['variant'], 'PLO6')

    def test_wrong_card_count_rejected(self):
        self.changed(lambda x: x['hands'][0]['events'][0].update(value=['AS', 'KH']))
        with self.assertRaises(ValueError): mod.export(self.video, self.observations, self.out)

    def test_duplicate_card_rejected(self):
        self.changed(lambda x: x['hands'][0]['events'][0].update(value=['AS'] * 5))
        with self.assertRaises(ValueError): mod.export(self.video, self.observations, self.out)

    def test_bad_card_rejected(self):
        self.changed(lambda x: x['hands'][0]['events'][0]['value'].__setitem__(0, '1X'))
        with self.assertRaises(ValueError): mod.export(self.video, self.observations, self.out)

    def test_board_conflict_flagged_not_asserted(self):
        self.changed(lambda x: x['hands'][0]['events'][3]['value'].__setitem__(0, '6C'))
        result = mod.export(self.video, self.observations, self.out)
        self.assertIn('conflicting_board_proposals', result['hands'][0]['review_flags'])

    def test_hero_board_conflict_flagged(self):
        self.changed(lambda x: x['hands'][0]['events'][1]['value'].__setitem__(0, 'AS'))
        result = mod.export(self.video, self.observations, self.out)
        self.assertIn('hero_board_card_conflict', result['hands'][0]['review_flags'])

    def test_invalid_street_order_rejected(self):
        self.changed(lambda x: x['hands'][0]['events'][3].update(street='preflop'))
        with self.assertRaises(ValueError): mod.export(self.video, self.observations, self.out)

    def test_timestamp_outside_hand_rejected(self):
        self.changed(lambda x: x['hands'][0]['events'][0].update(timestamp_seconds=3.9))
        with self.assertRaises(ValueError): mod.export(self.video, self.observations, self.out)

    def test_confidence_out_of_range_rejected(self):
        self.changed(lambda x: x['hands'][0]['events'][0].update(confidence=1.5))
        with self.assertRaises(ValueError): mod.export(self.video, self.observations, self.out)

    def test_confidence_boolean_rejected(self):
        self.changed(lambda x: x['hands'][0]['events'][0].update(confidence=True))
        with self.assertRaises(ValueError): mod.export(self.video, self.observations, self.out)

    def test_source_hash_mismatch_rejected(self):
        self.changed(lambda x: x.update(source_video_sha256='0' * 64))
        with self.assertRaises(ValueError): mod.export(self.video, self.observations, self.out)

    def test_duplicate_hand_rejected(self):
        self.changed(lambda x: x['hands'].append(copy.deepcopy(x['hands'][0])))
        with self.assertRaises(ValueError): mod.export(self.video, self.observations, self.out)

    def test_more_than_four_tables_rejected(self):
        def change(x):
            for i in range(2, 6):
                hand = copy.deepcopy(x['hands'][0]); hand.update(table_id=f'T{i}')
                x['hands'].append(hand)
        self.changed(change)
        with self.assertRaises(ValueError): mod.export(self.video, self.observations, self.out)

    def test_collision_rejected(self):
        (self.out / mod.PAGE).write_text('already here')
        with self.assertRaises(ValueError): mod.export(self.video, self.observations, self.out)

    def test_output_symlink_rejected(self):
        link = self.root_out / 'link'
        link.symlink_to(self.out, target_is_directory=True)
        with self.assertRaises(ValueError): mod.export(self.video, self.observations, link)

    def test_duplicate_json_key_rejected(self):
        self.observations.write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaises(ValueError): mod.export(self.video, self.observations, self.out)

    def test_publish_failure_rolls_back(self):
        original = mod.os.link
        calls = {'n': 0}
        def fail_second(*args, **kwargs):
            calls['n'] += 1
            if calls['n'] == 2: raise OSError('simulated publication failure')
            return original(*args, **kwargs)
        with mock.patch.object(mod.os, 'link', side_effect=fail_second):
            with self.assertRaises(OSError): mod.export(self.video, self.observations, self.out)
        self.assertEqual(list(self.out.iterdir()), [])

    def test_no_events_allowed_with_review(self):
        self.changed(lambda x: x['hands'][0].update(events=[]))
        result = mod.export(self.video, self.observations, self.out)
        self.assertEqual(result['hands'][0]['event_count'], 0)
        self.assertTrue(result['hands'][0]['review_required'])


if __name__ == '__main__':
    unittest.main()
