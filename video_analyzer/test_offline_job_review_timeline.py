"""Synthetic tests for an evidence-only, fail-closed OCR review timeline."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from offline_job_review_decisions import handoff_sha256, validate_submission
from offline_job_review_timeline import (build_timeline, verify_saved_review,
                                         load_report, timeline_job, export_timeline)


class TimelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.job_id = 'c' * 32
        self.folder = self.root / self.job_id
        self.folder.mkdir()
        self.store = Mock()
        self.handoff = {
            'schema_version': 1, 'analysis_status': 'unapproved_offline_review_handoff',
            'requires_manual_review': True, 'ready_for_equity_or_ev': False,
            'automatic_clip_selection_authorized': False, 'hand_reconstruction_verified': False,
            'job_id': self.job_id, 'source_sha256': 'a' * 64,
            'timestamp_semantics': 'nominal_sampling_grid_not_exact_source_pts',
            'manifest_frame_hashes_matched': True, 'frame_count': 4, 'ocr_hint_count': 4,
            'frames': [
                {'table_id': t, 'nominal_timestamp_seconds': float(t - 1),
                 'image': f'table_0{t}/frame_00000.png', 'sha256': f'{t}' * 64,
                 'ocr_hints_unverified': [{'field': 'pot', 'candidate_index': t,
                                           'unverified_text': str(100 * t)}]}
                for t in (1, 2, 3, 4)
            ]
        }
        self.submission = {
            'schema_version': 1, 'job_id': self.job_id,
            'handoff_sha256': handoff_sha256(self.handoff),
            'reviewer': 'reviewer-1',
            'decisions': [self.decision(1, 'confirmed', '100', .99),
                          self.decision(2, 'corrected', '250', .75),
                          self.decision(3, 'uncertain', None, None)],
        }
        self.saved = validate_submission(self.handoff, self.submission)
        self.report_path = self.folder / 'human_ocr_review.json'
        self.write_report()

    def decision(self, table, status, value, confidence):
        return {'table_id': table, 'nominal_timestamp_seconds': float(table - 1),
                'field': 'pot', 'candidate_index': table, 'status': status,
                'value': value, 'confidence': confidence,
                'reason': 'Revisão humana explícita'}

    def write_report(self):
        self.report_path.write_text(json.dumps(self.saved), encoding='utf-8')

    def build(self):
        raw = self.report_path.read_bytes()
        return build_timeline(self.handoff, self.saved, hashlib.sha256(raw).hexdigest())

    def test_four_table_timeline_and_pending(self):
        timeline = self.build()
        self.assertEqual([x['table_id'] for x in timeline['observations']], [1, 2, 3, 4])
        self.assertEqual(timeline['counts']['pending'], 1)
        self.assertEqual(timeline['counts']['reviewed'], 3)
        self.assertEqual(timeline['counts']['confirmed'], 1)
        self.assertEqual(timeline['counts']['corrected'], 1)
        self.assertEqual(timeline['counts']['uncertain'], 1)
        self.assertFalse(timeline['ready_for_equity_or_ev'])
        self.assertFalse(timeline['automatic_clip_selection_authorized'])

    def test_values_only_on_approved_human_annotations(self):
        entries = self.build()['observations']
        self.assertEqual(entries[0]['human_annotation_value'], '100')
        self.assertEqual(entries[1]['human_annotation_value'], '250')
        self.assertIsNone(entries[2]['human_annotation_value'])
        self.assertIsNone(entries[3]['human_annotation_value'])
        self.assertEqual(entries[2]['review_status'], 'uncertain')
        self.assertEqual(entries[3]['review_status'], 'pending')

    def test_rejected_has_no_value(self):
        self.submission['decisions'][2] = self.decision(3, 'rejected', None, None)
        self.saved = validate_submission(self.handoff, self.submission)
        self.write_report()
        self.assertEqual(self.build()['observations'][2]['review_status'], 'rejected')

    def test_complete_review_still_blocks_math(self):
        self.submission['decisions'].append(self.decision(4, 'confirmed', '400', .8))
        self.saved = validate_submission(self.handoff, self.submission)
        self.write_report()
        timeline = self.build()
        self.assertEqual(timeline['counts']['pending'], 0)
        self.assertFalse(timeline['hand_reconstruction_verified'])
        self.assertFalse(timeline['ready_for_equity_or_ev'])

    def test_modified_value_rejected(self):
        self.saved['decisions'][0]['value'] = '999'
        with self.assertRaises(ValueError): self.build()

    def test_modified_review_count_rejected(self):
        self.saved['reviewed_count'] = 99
        with self.assertRaisesRegex(ValueError, 'differs'): self.build()

    def test_added_math_flag_rejected(self):
        self.saved['ready_for_equity_or_ev'] = True
        with self.assertRaises(ValueError): self.build()

    def test_ocr_original_text_tamper_rejected(self):
        self.saved['decisions'][0]['original_ocr_text_unverified'] = '999'
        with self.assertRaisesRegex(ValueError, 'differs'): self.build()

    def test_changed_handoff_rejected(self):
        self.handoff['frames'][0]['ocr_hints_unverified'][0]['unverified_text'] = '101'
        with self.assertRaises(ValueError): self.build()

    def test_bad_image_path_rejected(self):
        self.handoff['frames'][0]['image'] = '../../secrets'
        self.saved = validate_submission(self.handoff, {
            **self.submission, 'handoff_sha256': handoff_sha256(self.handoff)})
        with self.assertRaisesRegex(ValueError, 'image reference'): self.build()

    def test_bad_image_digest_rejected(self):
        self.handoff['frames'][0]['sha256'] = 'not-a-sha'
        self.saved = validate_submission(self.handoff, {
            **self.submission, 'handoff_sha256': handoff_sha256(self.handoff)})
        with self.assertRaisesRegex(ValueError, 'image reference'): self.build()

    def test_bad_hint_count_rejected(self):
        self.handoff['ocr_hint_count'] = 5
        self.saved = validate_submission(self.handoff, {
            **self.submission, 'handoff_sha256': handoff_sha256(self.handoff)})
        with self.assertRaisesRegex(ValueError, 'count mismatch'): self.build()

    def test_symlink_report_rejected(self):
        link = self.root / 'link.json'
        link.symlink_to(self.report_path)
        with self.assertRaises(OSError): load_report(link)

    def test_duplicate_json_key_rejected(self):
        self.report_path.write_text('{"job_id":"a","job_id":"b"}', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Duplicate'): load_report(self.report_path)

    def test_nonfinite_json_rejected(self):
        self.report_path.write_text('{"confidence": NaN}', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Nonfinite'): load_report(self.report_path)

    def test_report_size_limit(self):
        self.report_path.write_bytes(b' ' * (16 * 1024 * 1024 + 1))
        with self.assertRaisesRegex(ValueError, 'size'): load_report(self.report_path)

    def test_job_reaudits_source_and_report(self):
        with patch('offline_job_review_timeline.build_handoff', return_value=self.handoff) as audit:
            result = timeline_job(self.store, self.job_id, self.root)
        audit.assert_called_once_with(self.store, self.job_id, self.root)
        self.assertEqual(result['counts']['ocr_hints'], 4)
        self.store.transition.assert_not_called()

    def test_export_is_write_once(self):
        with patch('offline_job_review_timeline.build_handoff', return_value=self.handoff):
            exported = export_timeline(self.store, self.job_id, self.root)
            output = self.folder / 'human_ocr_timeline.json'
            self.assertEqual(json.loads(output.read_text())['counts']['ocr_hints'], 4)
            with self.assertRaises(FileExistsError): export_timeline(self.store, self.job_id, self.root)
        self.assertFalse(exported['ready_for_equity_or_ev'])
        self.store.transition.assert_not_called()

    def test_report_changed_since_review_rejected(self):
        self.saved['decisions'][0]['original_ocr_text_unverified'] = '999'
        self.write_report()
        with patch('offline_job_review_timeline.build_handoff', return_value=self.handoff):
            with self.assertRaises(ValueError): timeline_job(self.store, self.job_id, self.root)

    def test_reject_invalid_job_id(self):
        with self.assertRaisesRegex(ValueError, 'job ID'):
            timeline_job(self.store, '../../bad', self.root)

    def test_real_source_audit_and_image_tamper(self):
        from test_offline_job_review_handoff import HandoffTests
        fixture = HandoffTests('test_unapproved_ocr_linked')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.ocr(text='120', field='pot')
        handoff = fixture.build()
        decision = {'table_id': 1, 'nominal_timestamp_seconds': 0.0,
                    'field': 'pot', 'candidate_index': 0, 'status': 'confirmed',
                    'value': '120', 'confidence': .8, 'reason': 'Valor conferido'}
        sub = {'schema_version': 1, 'job_id': fixture.job_id,
               'handoff_sha256': handoff_sha256(handoff), 'reviewer': 'reviewer',
               'decisions': [decision]}
        report = validate_submission(handoff, sub)
        path = fixture.folder / 'human_ocr_review.json'
        path.write_text(json.dumps(report), encoding='utf-8')
        result = timeline_job(fixture.store, fixture.job_id, fixture.root / 'results')
        self.assertEqual(result['counts']['reviewed'], 1)
        self.assertEqual(result['observations'][0]['source_image_sha256'],
                         hashlib.sha256(fixture.image.read_bytes()).hexdigest())
        fixture.image.write_bytes(fixture.image.read_bytes() + b'tampered')
        with self.assertRaises(ValueError):
            timeline_job(fixture.store, fixture.job_id, fixture.root / 'results')


if __name__ == '__main__':
    unittest.main()
