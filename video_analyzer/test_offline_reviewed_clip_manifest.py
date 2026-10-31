"""Synthetic-only verification of reviewed evidence to MP4 navigation."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

import offline_reviewed_clip_manifest as mod


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class ReviewedClipManifestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='plo_reviewed_clip_test_')
        self.root = Path(self.tmp.name)
        self.split = self.root / 'clips'
        self.out = self.root / 'result'
        self.split.mkdir()
        self.out.mkdir()
        self.review_path = self.root / 'review.json'
        self.index_path = self.root / 'index.json'
        self.video_sha = 'a' * 64
        self.street_sha = 'b' * 64
        self.review = {'schema_version': 1,
                       'status': 'offline_human_reviewed_evidence_not_math_authorized',
                       'variant': 'PLO5', 'source_video_sha256': self.video_sha,
                       'source_street_report_sha256': self.street_sha,
                       'confidence_calibrated': False,
                       'automatic_ocr_math_authorization': False,
                       'reviewer_label': 'human_1', 'hands': []}
        self.index = {'schema_version': 1,
                      'status': 'offline_street_split_index_review_required',
                      'variant': 'PLO5', 'source_video_sha256': self.video_sha,
                      'source_street_report_sha256': self.street_sha,
                      'confidence_calibrated': False, 'table_identity_verified': False,
                      'automatic_ocr_math_authorization': False,
                      'hands': [], 'unlinked_clips': [], 'blocked_clips': []}
        self.add_hand('T1', 'H1', 'confirm')
        self.save()

    def tearDown(self):
        self.tmp.cleanup()

    def add_hand(self, table, hid, decision):
        original = {'timestamp_seconds': 1.0, 'kind': 'action', 'value': 'call',
                    'origin': 'ocr_proposal', 'confidence': .4}
        reviewed = {'event_index': 0, 'timestamp_seconds': 1.0, 'street': 'flop',
                    'kind': 'action', 'decision': decision, 'original_value': 'call',
                    'reviewed_value': None if decision == 'reject' else ('fold' if decision == 'correct' else 'call'),
                    'reason': 'not visible' if decision == 'reject' else ('checked frames' if decision == 'correct' else ''),
                    'origin': 'ocr_proposal', 'proposal_confidence_uncalibrated': .4}
        filename = f'split_{table}_{hid}_s01.mp4'
        path = self.split / filename
        if shutil.which('ffmpeg'):
            subprocess.run(['ffmpeg', '-nostdin', '-loglevel', 'error', '-y', '-f', 'lavfi',
                            '-i', 'color=c=black:s=64x64:r=5', '-t', '1', '-an',
                            '-c:v', 'mpeg4', str(path)], check=True, timeout=20)
        else:
            path.write_bytes(b'\x00\x00\x00\x18ftypisom' + b'0' * 32)
        self.review['hands'].append({'table_id': table, 'hand_id': hid,
             'start_seconds': 0.0, 'end_seconds': 2.0, 'events': [reviewed],
             'review_flags': [], 'card_evidence_consistent': True,
             'automatic_math_authorization': False})
        self.index['hands'].append({'table_id': table, 'hand_id': hid,
             'start_seconds': 0.0, 'end_seconds': 2.0, 'streets': {'flop': [original]},
             'clips': [{'clip_id': f'C_{table}_{hid}', 'table_id': table, 'hand_id': hid,
                        'segment_index': 1, 'filename': filename, 'sha256': sha(path),
                        'start_seconds': .5, 'end_seconds': 1.5, 'decision_in_part': True}],
             'automatic_math_authorization': False})

    def save(self):
        self.review_path.write_text(json.dumps(self.review), encoding='utf-8')
        self.index_path.write_text(json.dumps(self.index), encoding='utf-8')

    def run_export(self):
        self.save()
        return mod.export(self.review_path, self.index_path, self.split, self.out)

    def test_export_one_hand(self):
        result = self.run_export()
        self.assertEqual(len(result['hands']), 1)
        self.assertEqual(result['hands'][0]['events'][0]['decision'], 'confirm')
        self.assertFalse(result['automatic_math_authorization'])
        self.assertEqual({p.name for p in self.out.iterdir()}, {mod.REPORT, mod.PAGE})
        self.assertEqual(json.loads((self.out / mod.REPORT).read_text())['source_reviewed_report_sha256'], sha(self.review_path))

    def test_four_tables_and_rejected_decision(self):
        self.review['hands'][0]['events'][0].update(decision='reject', reviewed_value=None, reason='hidden')
        for n in range(2, 5):
            self.add_hand(f'T{n}', f'H{n}', 'correct')
        result = self.run_export()
        self.assertEqual(len(result['hands']), 4)
        self.assertEqual(sum(len(h['clips']) for h in result['hands']), 4)
        self.assertIsNone(result['hands'][0]['events'][0]['value'])
        self.assertEqual(result['hands'][1]['events'][0]['value'], 'fold')

    def test_html_escapes_reviewed_text(self):
        self.review['hands'][0]['events'][0].update(decision='correct',
            reviewed_value='<img src=x onerror=alert(1)>', reason='checked')
        self.run_export()
        html = (self.out / mod.PAGE).read_text()
        self.assertIn('&lt;img', html)
        self.assertNotIn('<img', html)

    def test_relative_media_path(self):
        self.run_export()
        self.assertIn('../clips/split_T1_H1_s01.mp4', (self.out / mod.PAGE).read_text())

    def test_reject_mismatched_video_hash(self):
        self.index['source_video_sha256'] = 'c' * 64
        with self.assertRaises(ValueError): self.run_export()

    def test_reject_mismatched_street_hash(self):
        self.index['source_street_report_sha256'] = 'c' * 64
        with self.assertRaises(ValueError): self.run_export()

    def test_reject_math_authorization(self):
        self.review['automatic_ocr_math_authorization'] = True
        with self.assertRaises(ValueError): self.run_export()

    def test_reject_calibrated_confidence_claim(self):
        self.index['confidence_calibrated'] = True
        with self.assertRaises(ValueError): self.run_export()

    def test_reject_unverified_table_claim(self):
        self.index['table_identity_verified'] = True
        with self.assertRaises(ValueError): self.run_export()

    def test_reject_event_value_mismatch(self):
        self.review['hands'][0]['events'][0]['original_value'] = 'raise'
        with self.assertRaises(ValueError): self.run_export()

    def test_reject_event_index_mismatch(self):
        self.review['hands'][0]['events'][0]['event_index'] = 3
        with self.assertRaises(ValueError): self.run_export()

    def test_reject_duplicate_hand(self):
        self.review['hands'].append(copy.deepcopy(self.review['hands'][0]))
        with self.assertRaises(ValueError): self.run_export()

    def test_reject_duplicate_clip(self):
        self.index['hands'][0]['clips'].append(copy.deepcopy(self.index['hands'][0]['clips'][0]))
        with self.assertRaises(ValueError): self.run_export()

    def test_reject_tampered_mp4(self):
        with (self.split / 'split_T1_H1_s01.mp4').open('ab') as f:
            f.write(b'tamper')
        with self.assertRaises(ValueError): self.run_export()

    def test_reject_traversal(self):
        self.index['hands'][0]['clips'][0]['filename'] = '../escape.mp4'
        with self.assertRaises(ValueError): self.run_export()

    def test_reject_symlink_mp4(self):
        path = self.split / 'split_T1_H1_s01.mp4'
        target = self.root / 'elsewhere.mp4'
        path.rename(target)
        path.symlink_to(target)
        with self.assertRaises(ValueError): self.run_export()

    def test_reject_output_collision(self):
        (self.out / mod.PAGE).write_text('existing')
        with self.assertRaises(ValueError): self.run_export()

    def test_reject_duplicate_json_keys(self):
        self.save()
        self.review_path.write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaises(ValueError):
            mod.export(self.review_path, self.index_path, self.split, self.out)

    def test_reject_bad_correction(self):
        self.review['hands'][0]['events'][0].update(decision='correct', reviewed_value='call', reason='checked')
        with self.assertRaises(ValueError): self.run_export()

    def test_reject_bad_rejection(self):
        self.review['hands'][0]['events'][0].update(decision='reject', reviewed_value=None, reason='')
        with self.assertRaises(ValueError): self.run_export()

    def test_plo6_variant_navigation(self):
        self.review['variant'] = 'PLO6'
        self.index['variant'] = 'PLO6'
        result = self.run_export()
        self.assertEqual(result['variant'], 'PLO6')
        self.assertFalse(result['automatic_math_authorization'])

    def test_blocked_and_unlinked_counts_preserved(self):
        self.index['blocked_clips'] = [{'clip_id': 'blocked_1', 'reason': 'transition'}]
        self.index['unlinked_clips'] = [{'clip_id': 'unlinked_1', 'reason': 'unknown_hand'}]
        result = self.run_export()
        self.assertEqual((result['blocked_clip_count'], result['unlinked_clip_count']), (1, 1))

    def test_reject_clip_wrong_table(self):
        self.index['hands'][0]['clips'][0]['table_id'] = 'T2'
        with self.assertRaises(ValueError): self.run_export()

    def test_reject_output_symlink(self):
        link = self.root / 'output_link'
        link.symlink_to(self.out, target_is_directory=True)
        self.save()
        with self.assertRaises(ValueError):
            mod.export(self.review_path, self.index_path, self.split, link)

    def test_reject_invalid_variant(self):
        self.review['variant'] = 'PLO4'
        self.index['variant'] = 'PLO4'
        with self.assertRaises(ValueError): self.run_export()

    def test_atomic_rollback(self):
        real = mod.os.link
        count = [0]
        def fail_second(src, dest):
            count[0] += 1
            if count[0] == 2:
                raise OSError('synthetic failure')
            return real(src, dest)
        with mock.patch.object(mod.os, 'link', side_effect=fail_second):
            with self.assertRaises(OSError): self.run_export()
        self.assertEqual(list(self.out.iterdir()), [])


if __name__ == '__main__':
    unittest.main()
