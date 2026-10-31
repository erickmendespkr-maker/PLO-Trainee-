"""Synthetic-only tests for explicit human review; no poker-client integration."""
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

import offline_ev_table_crop as media
import offline_street_evidence as street
import offline_street_human_review as mod


class HumanReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = tempfile.TemporaryDirectory(prefix='plo_review_fixture_')
        cls.root = Path(cls.fixture.name)
        cls.video = cls.root / 'synthetic.mp4'
        subprocess.run(['ffmpeg', '-nostdin', '-loglevel', 'error', '-y', '-f', 'lavfi',
                        '-i', 'testsrc2=size=160x120:rate=10', '-t', '4', '-an',
                        '-c:v', 'mpeg4', '-q:v', '4', str(cls.video)], check=True,
                       capture_output=True, timeout=30)
        cls.obs = cls.root / 'observations.json'
        cls.observations = {'schema_version': 1,
            'status': 'offline_unverified_street_observations',
            'source_video_sha256': media.digest(cls.video), 'variant': 'PLO5',
            'hands': [{'table_id': 'T1', 'hand_id': 'H1', 'start_seconds': .2,
                       'end_seconds': 3.8, 'events': [
                {'timestamp_seconds': .4, 'street': 'preflop', 'kind': 'hero_cards',
                 'value': ['AS', 'KH', 'QD', 'JC', 'TS'], 'origin': 'ocr_proposal', 'confidence': .55},
                {'timestamp_seconds': 1, 'street': 'flop', 'kind': 'board',
                 'value': ['2C', '3D', '4H'], 'origin': 'ocr_proposal', 'confidence': .8},
                {'timestamp_seconds': 1.5, 'street': 'flop', 'kind': 'action',
                 'value': 'call', 'origin': 'ocr_proposal', 'confidence': .3},
                {'timestamp_seconds': 2, 'street': 'turn', 'kind': 'board',
                 'value': ['2C', '3D', '4H', '5S'], 'origin': 'manual_claim', 'confidence': 1.0}]}]}
        cls.obs.write_text(json.dumps(cls.observations), encoding='utf-8')
        cls.street_dir = cls.root / 'street'
        cls.street_dir.mkdir()
        street.export(cls.video, cls.obs, cls.street_dir)

    @classmethod
    def tearDownClass(cls):
        cls.fixture.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='plo_review_case_')
        self.folder = Path(self.temp.name)
        self.out = self.folder / 'out'
        self.out.mkdir()
        self.review_file = self.folder / 'review.json'
        self.review = {'schema_version': 1, 'status': 'manual_offline_street_review',
                       'source_street_report_sha256': media.digest(self.street_dir / street.REPORT),
                       'reviewer_label': 'operator_1', 'hands': [
            {'table_id': 'T1', 'hand_id': 'H1', 'decisions': [
                {'event_index': i, 'decision': 'confirm', 'value': None, 'reason': ''}
                for i in range(4)]}]}
        self.save()

    def tearDown(self):
        self.temp.cleanup()

    def save(self):
        self.review_file.write_text(json.dumps(self.review, ensure_ascii=False), encoding='utf-8')

    def run_export(self):
        self.save()
        return mod.export(self.video, self.obs, self.street_dir, self.review_file, self.out)

    def test_all_confirmed_generates_report_and_html(self):
        report = self.run_export()
        self.assertEqual(report['status'], mod.STATUS)
        self.assertFalse(report['automatic_ocr_math_authorization'])
        self.assertFalse(report['hands'][0]['automatic_math_authorization'])
        self.assertTrue(report['hands'][0]['card_evidence_consistent'])
        self.assertEqual(report['hands'][0]['rejected_event_count'], 0)
        self.assertEqual({p.name for p in self.out.iterdir()}, {mod.REPORT, mod.PAGE})
        self.assertEqual(json.loads((self.out / mod.REPORT).read_text())['source_manual_review_sha256'],
                         media.digest(self.review_file))

    def test_correction_records_provenance(self):
        self.review['hands'][0]['decisions'][2] = {'event_index': 2, 'decision': 'correct',
                                                  'value': 'fold', 'reason': 'frame manually checked'}
        item = self.run_export()['hands'][0]['events'][2]
        self.assertEqual((item['original_value'], item['reviewed_value']), ('call', 'fold'))
        self.assertEqual(item['origin'], 'ocr_proposal')

    def test_reject_requires_reason_and_does_not_retain_value(self):
        self.review['hands'][0]['decisions'][2] = {'event_index': 2, 'decision': 'reject',
                                                  'value': None, 'reason': 'obscured'}
        hand = self.run_export()['hands'][0]
        self.assertEqual(hand['rejected_event_count'], 1)
        self.assertIsNone(hand['events'][2]['reviewed_value'])

    def test_board_overlap_flagged_even_after_confirmation(self):
        self.review['hands'][0]['decisions'][1] = {'event_index': 1, 'decision': 'correct',
            'value': ['AS', '3D', '4H'], 'reason': 'human correction'}
        hand = self.run_export()['hands'][0]
        self.assertIn('hero_board_overlap', hand['review_flags'])
        self.assertIn('conflicting_reviewed_board', hand['review_flags'])
        self.assertFalse(hand['card_evidence_consistent'])

    def test_reject_duplicate_event(self):
        self.review['hands'][0]['decisions'][1]['event_index'] = 0
        with self.assertRaises(ValueError): self.run_export()

    def test_reject_missing_decision(self):
        self.review['hands'][0]['decisions'].pop()
        with self.assertRaises(ValueError): self.run_export()

    def test_reject_unsafe_card(self):
        self.review['hands'][0]['decisions'][1] = {'event_index': 1, 'decision': 'correct',
            'value': ['2C', '2C', '4H'], 'reason': 'corrected'}
        with self.assertRaises(ValueError): self.run_export()

    def test_reject_wrong_hero_count(self):
        self.review['hands'][0]['decisions'][0] = {'event_index': 0, 'decision': 'correct',
            'value': ['AS', 'KH', 'QD', 'JC'], 'reason': 'corrected'}
        with self.assertRaises(ValueError): self.run_export()

    def test_reject_empty_reason_on_correction(self):
        self.review['hands'][0]['decisions'][2] = {'event_index': 2, 'decision': 'correct',
            'value': 'fold', 'reason': ''}
        with self.assertRaises(ValueError): self.run_export()

    def test_reject_value_in_confirmation(self):
        self.review['hands'][0]['decisions'][2]['value'] = 'fold'
        with self.assertRaises(ValueError): self.run_export()

    def test_reject_unknown_hand(self):
        self.review['hands'][0]['hand_id'] = 'OTHER'
        with self.assertRaises(ValueError): self.run_export()

    def test_reject_review_hash_mismatch(self):
        self.review['source_street_report_sha256'] = '0' * 64
        with self.assertRaises(ValueError): self.run_export()

    def test_reject_duplicate_json_keys(self):
        self.review_file.write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaises(ValueError): mod.export(
            self.video, self.obs, self.street_dir, self.review_file, self.out)

    def test_reject_html_injection_escaped(self):
        self.review['hands'][0]['decisions'][2] = {'event_index': 2, 'decision': 'correct',
            'value': '<img src=x onerror=alert(1)>', 'reason': 'visually verified'}
        self.run_export()
        html = (self.out / mod.PAGE).read_text()
        self.assertIn('&lt;img', html)
        self.assertNotIn('<img', html)

    def test_reject_output_collision(self):
        (self.out / mod.REPORT).write_text('existing')
        with self.assertRaises(ValueError): self.run_export()

    def test_reject_output_symlink(self):
        target = self.folder / 'symlink'
        target.symlink_to(self.out, target_is_directory=True)
        self.save()
        with self.assertRaises(ValueError): mod.export(
            self.video, self.obs, self.street_dir, self.review_file, target)

    def test_detect_tampered_street_report(self):
        tampered = self.folder / 'tampered'
        tampered.mkdir()
        ledger = json.loads((self.street_dir / street.REPORT).read_text())
        ledger['hands'][0]['event_count'] = 999
        (tampered / street.REPORT).write_text(json.dumps(ledger))
        self.save()
        with self.assertRaises(ValueError): mod.export(
            self.video, self.obs, tampered, self.review_file, self.out)

    def test_rollback_on_publish_failure(self):
        original = mod.os.link
        counter = [0]
        def fail_second(src, dst):
            counter[0] += 1
            if counter[0] == 2: raise OSError('simulated publish failure')
            return original(src, dst)
        with mock.patch.object(mod.os, 'link', side_effect=fail_second):
            with self.assertRaises(OSError): self.run_export()
        self.assertEqual(list(self.out.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
