"""Synthetic-only evidence-to-split MP4 index tests; no real poker footage."""
import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

import offline_ev_table_crop as crop
import offline_street_evidence as street
import offline_temporal_split_clips as split
import offline_street_split_index as join
from test_offline_temporal_batch_crops import TemporalBatchTests, write


class StreetSplitIndexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        TemporalBatchTests.setUpClass.__func__(cls)
        cls.observations = cls.root / 'observations.json'
        cls.street_dir = cls.root / 'street'
        cls.street_dir.mkdir()
        cls.split_dir = cls.root / 'split'
        cls.split_dir.mkdir()
        hands = []
        for i in range(1, 5):
            hands.append({'table_id': f'T{i}', 'hand_id': f'H{i}',
                          'start_seconds': .1, 'end_seconds': 5.8,
                          'events': [{'timestamp_seconds': .5, 'street': 'preflop',
                                      'kind': 'hero_cards',
                                      'value': ['AS','KH','QD','JC','TS'],
                                      'origin': 'ocr_proposal', 'confidence': .45},
                                     {'timestamp_seconds': 1.5, 'street': 'flop',
                                      'kind': 'board', 'value': ['2C','3D','4H'],
                                      'origin': 'manual_claim', 'confidence': 1.0},
                                     {'timestamp_seconds': 2.0, 'street': 'flop',
                                      'kind': 'action', 'value': '<img src=x onerror=alert(1)>',
                                      'origin': 'ocr_proposal', 'confidence': .4}]})
        write(cls.observations, {'schema_version': 1,
              'status': 'offline_unverified_street_observations',
              'source_video_sha256': crop.digest(cls.video),
              'variant': 'PLO5', 'hands': hands})
        street.export(cls.video, cls.observations, cls.street_dir)
        split.export(cls.video, cls.batch_dir, cls.review, cls.split_dir)

    @classmethod
    def tearDownClass(cls):
        TemporalBatchTests.tearDownClass.__func__(cls)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='plo_join_test_')
        root = Path(self.tmp.name)
        self.out = root / 'split'
        self.streets = root / 'street'
        shutil.copytree(self.split_dir, self.out)
        shutil.copytree(self.street_dir, self.streets)
        self.obs = root / 'observations.json'
        shutil.copy2(self.observations, self.obs)

    def tearDown(self):
        self.tmp.cleanup()

    def run_export(self, **kw):
        return join.export(kw.get('video', self.video), kw.get('obs', self.obs),
                           kw.get('streets', self.streets),
                           kw.get('batch', self.batch_dir),
                           kw.get('review', self.review),
                           kw.get('out', self.out))

    def mutate(self, path, change):
        data = json.loads(path.read_text())
        change(data)
        write(path, data)

    def test_index_four_hands_four_mp4_and_blocked(self):
        result = self.run_export()
        self.assertEqual(len(result['hands']), 4)
        self.assertEqual(sum(len(h['clips']) for h in result['hands']), 4)
        self.assertEqual(len(result['blocked_clips']), 1)
        self.assertEqual(len(result['unlinked_clips']), 0)
        self.assertFalse(result['automatic_ocr_math_authorization'])
        self.assertEqual((self.out / join.PAGE).read_text().count('<video '), 4)
        self.assertEqual(result['source_video_sha256'], crop.digest(self.video))

    def test_html_escapes_untrusted_text_and_no_script(self):
        self.run_export()
        html = (self.out / join.PAGE).read_text()
        self.assertIn('&lt;img src=x onerror=alert(1)&gt;', html)
        self.assertNotIn('<img', html)
        self.assertNotIn('<script', html)
        self.assertIn('não é calibrada', html)

    def test_evidence_not_automatically_approved(self):
        result = self.run_export()
        self.assertTrue(all(h['review_required'] and not h['automatic_math_authorization']
                            for h in result['hands']))
        self.assertTrue(all(not h['clips'][0].get('verified', False) for h in
                            result['hands'] if h['clips']))

    def test_street_report_mutation_rejected(self):
        self.mutate(self.streets / street.REPORT,
                    lambda d: d['hands'][0].update(review_required=False))
        with self.assertRaises(ValueError): self.run_export()

    def test_observations_mutation_rejected(self):
        self.mutate(self.obs, lambda d: d['hands'][0]['events'][0].update(confidence=.99))
        with self.assertRaises(ValueError): self.run_export()

    def test_wrong_video_rejected(self):
        other = Path(self.tmp.name) / 'wrong.mp4'
        other.write_bytes(self.video.read_bytes() + b'mutated')
        with self.assertRaises(ValueError): self.run_export(video=other)

    def test_split_ledger_mutation_rejected(self):
        self.mutate(self.out / 'temporal_split_report.json',
                    lambda d: d['parts'][0].update(start_seconds=0.6))
        with self.assertRaises(ValueError): self.run_export()

    def test_modified_mp4_rejected(self):
        with (self.out / 'split_first_s01.mp4').open('ab') as f:
            f.write(b'bad')
        with self.assertRaises(ValueError): self.run_export()

    def test_modified_metadata_rejected(self):
        self.mutate(self.out / 'split_first_s01.json',
                    lambda d: d.update(table_identity_verified=True))
        with self.assertRaises(ValueError): self.run_export()

    def test_missing_mp4_rejected(self):
        (self.out / 'split_first_s01.mp4').unlink()
        with self.assertRaises(ValueError): self.run_export()

    def test_symlink_mp4_rejected(self):
        mp4 = self.out / 'split_first_s01.mp4'
        target = Path(self.tmp.name) / 'target.mp4'
        mp4.rename(target)
        mp4.symlink_to(target)
        with self.assertRaises(ValueError): self.run_export()

    def test_duplicate_output_rejected(self):
        self.run_export()
        with self.assertRaises(ValueError): self.run_export()

    def test_unlinked_clip_is_flagged_not_merged(self):
        self.mutate(self.obs, lambda d: d['hands'][0].update(hand_id='OTHER'))
        # Rebuild street report from the modified observations; the clip now lacks a matching hand.
        (self.streets / street.REPORT).unlink()
        (self.streets / street.PAGE).unlink()
        street.export(self.video, self.obs, self.streets)
        result = self.run_export()
        self.assertEqual(len(result['unlinked_clips']), 1)
        self.assertEqual(result['unlinked_clips'][0]['reason'], 'no_matching_street_hand')
        self.assertEqual(sum(len(h['clips']) for h in result['hands']), 3)

    def test_decision_outside_hand_interval_is_not_linked(self):
        self.mutate(self.obs, lambda d: d['hands'][0].update(end_seconds=.8,
                     events=d['hands'][0]['events'][:1]))
        (self.streets / street.REPORT).unlink()
        (self.streets / street.PAGE).unlink()
        street.export(self.video, self.obs, self.streets)
        result = self.run_export()
        self.assertEqual(result['unlinked_clips'][0]['reason'],
                         'decision_outside_street_hand_interval')

    def test_publication_failure_rolls_back(self):
        original = join.os.link
        calls = {'n': 0}
        def fail(*args, **kwargs):
            calls['n'] += 1
            if calls['n'] == 2: raise OSError('simulated write failure')
            return original(*args, **kwargs)
        with mock.patch.object(join.os, 'link', side_effect=fail):
            with self.assertRaises(OSError): self.run_export()
        self.assertFalse((self.out / join.PAGE).exists())
        self.assertFalse((self.out / join.REPORT).exists())

    def test_unsafe_output_symlink_rejected(self):
        link = Path(self.tmp.name) / 'link'
        link.symlink_to(self.out, target_is_directory=True)
        with self.assertRaises(ValueError): self.run_export(out=link)

    def test_source_batch_mutation_rejected(self):
        bad_batch = Path(self.tmp.name) / 'bad_batch'
        shutil.copytree(self.batch_dir, bad_batch)
        with (bad_batch / 'first.mp4').open('ab') as f:
            f.write(b'bad')
        with self.assertRaises(ValueError): self.run_export(batch=bad_batch)

    def test_duplicate_json_keys_rejected(self):
        (self.streets / street.REPORT).write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaises(ValueError): self.run_export()


if __name__ == '__main__':
    unittest.main()
