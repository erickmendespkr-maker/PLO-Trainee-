"""Tests for offline hash-bound activity OCR -> human review provenance."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from activity_evidence_export import export_activity_evidence
from activity_ocr_bridge import scan_activity_ocr
from activity_review_chain import (create_activity_review_template,
                                   bridge_activity_review, run_activity_review)
from table_regions import Region
from video_validator import validate_recording


class ActivityReviewChainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.video = Path(cls.tmp.name) / 'synthetic.mp4'
        subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
                        '-f', 'lavfi', '-i', 'testsrc2=size=160x120:rate=4:duration=2',
                        '-c:v', 'mpeg4', str(cls.video)], check=True, capture_output=True)
        cls.sha = hashlib.sha256(cls.video.read_bytes()).hexdigest()
        cls.duration = validate_recording(cls.video)['duration_seconds']

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def fixture(self, root, tables=(1,)):
        times = [.51, 1.01]
        plan = {'schema_version': 1, 'analysis_status': 'requested_offline_seek_plan_only',
                'timestamp_semantics': 'requested_seek_seconds_not_decoded_source_pts',
                'requires_manual_review': True, 'recording_sha256': self.sha,
                'duration_seconds': self.duration,
                'tables': [{'table_id': t, 'planned_count': len(times),
                            'requested_frames': [{'requested_seek_seconds': time,
                                                  'reason': 'baseline_grid'} for time in times]}
                           for t in tables],
                'planned_total_frames': len(times)*len(tables)}
        regions = [Region(t, (t-1)*80, 0, 80, 80) for t in tables]
        evidence = root / 'evidence'
        export_activity_evidence(self.video, plan, evidence, regions=regions)
        rois = {'tasks': [{'table_id': t, 'field': 'pot',
                           'region': {'x': 0, 'y': 0, 'width': 60, 'height': 40}}
                          for t in tables]}
        with patch('activity_ocr_bridge._run'), patch('activity_ocr_bridge.subprocess.run') as proc:
            proc.return_value.stdout = 'text\tconf\nPot\t95\n42.50\t95\n'
            report = scan_activity_ocr(evidence, rois, root / 'ocr.json')
        return evidence, rois, report

    def approved(self, template):
        review = copy.deepcopy(template)
        for index, event in enumerate(review['events']):
            event.update({'hand_id': f'hand_{event["table_id"]}', 'variant': 'PLO5',
                          'action': 'board', 'human_confirmed': True,
                          'reviewer_confidence': .95})
            for item in event['field_reviews'].values():
                item.update({'human_confirmed': True, 'reviewer_confidence': .9,
                             'approved_value': 42.5})
        return review

    def test_unapproved_template_with_bound_provenance(self):
        with tempfile.TemporaryDirectory() as d:
            evidence, rois, report = self.fixture(Path(d), tables=(1, 2))
            template = create_activity_review_template(evidence, rois, report)
            self.assertEqual(len(template['events']), 4)
            self.assertTrue(all(e['human_confirmed'] is False for e in template['events']))
            self.assertTrue(all(e['hand_id'] is None for e in template['events']))
            self.assertFalse(template['ready_for_equity_or_ev'])
            self.assertEqual(template['recording_sha256'], self.sha)
            self.assertEqual(len(template['ocr_report_sha256']), 64)

    def test_human_confirmed_bridge_no_ev_or_hidden_cards(self):
        with tempfile.TemporaryDirectory() as d:
            evidence, rois, report = self.fixture(Path(d))
            review = self.approved(create_activity_review_template(evidence, rois, report))
            result = bridge_activity_review(evidence, rois, report, review)
            self.assertEqual(len(result['observations']), 2)
            self.assertEqual(result['observations'][0]['pot'], 42.5)
            self.assertIsNone(result['observations'][0]['hero_cards'])
            self.assertFalse(result['ready_for_equity_or_ev'])
            self.assertEqual(result['provenance'][0]['evidence'][0]['source_image'],
                             report['candidates'][0]['source_image'])

    def test_reject_ocr_report_tampering_after_review_template(self):
        with tempfile.TemporaryDirectory() as d:
            evidence, rois, report = self.fixture(Path(d))
            review = self.approved(create_activity_review_template(evidence, rois, report))
            tampered = copy.deepcopy(report)
            tampered['candidates'][0]['raw_text'] = '999'
            with self.assertRaisesRegex(ValueError, 'binding'):
                bridge_activity_review(evidence, rois, tampered, review)

    def test_reject_forged_source_hash_and_pts(self):
        with tempfile.TemporaryDirectory() as d:
            evidence, rois, report = self.fixture(Path(d))
            for field, bad in [('source_sha256', '0'*64), ('source_pts_ticks', 42),
                               ('timestamp', 100.), ('requested_seeks', [999.])]:
                modified = copy.deepcopy(report)
                modified['candidates'][0][field] = bad
                with self.subTest(field=field), self.assertRaises(ValueError):
                    create_activity_review_template(evidence, rois, modified)

    def test_reject_modified_png_before_template_and_review(self):
        with tempfile.TemporaryDirectory() as d:
            evidence, rois, report = self.fixture(Path(d))
            review = self.approved(create_activity_review_template(evidence, rois, report))
            path = evidence / report['candidates'][0]['source_image']
            path.write_bytes(path.read_bytes() + b'tamper')
            with self.assertRaises(ValueError):
                create_activity_review_template(evidence, rois, report)
            with self.assertRaises(ValueError):
                bridge_activity_review(evidence, rois, report, review)

    def test_reject_unapproved_or_incomplete_events(self):
        with tempfile.TemporaryDirectory() as d:
            evidence, rois, report = self.fixture(Path(d))
            template = create_activity_review_template(evidence, rois, report)
            review = self.approved(template)
            for bad in (template, {**review, 'events': review['events'][:1]},
                        {**review, 'events': []}):
                with self.assertRaises(ValueError):
                    bridge_activity_review(evidence, rois, report, bad)

    def test_reject_cross_table_and_timestamp_reassignment(self):
        with tempfile.TemporaryDirectory() as d:
            evidence, rois, report = self.fixture(Path(d), tables=(1, 2))
            review = self.approved(create_activity_review_template(evidence, rois, report))
            for field, bad in [('table_id', 2), ('timestamp', 1.75)]:
                altered = copy.deepcopy(review)
                altered['events'][0][field] = bad
                with self.subTest(field=field), self.assertRaises(ValueError):
                    bridge_activity_review(evidence, rois, report, altered)

    def test_reject_candidate_swap_and_omission(self):
        with tempfile.TemporaryDirectory() as d:
            evidence, rois, report = self.fixture(Path(d))
            review = self.approved(create_activity_review_template(evidence, rois, report))
            altered = copy.deepcopy(review)
            altered['events'][0]['field_reviews']['pot']['candidate_index'] = 1
            with self.assertRaises(ValueError):
                bridge_activity_review(evidence, rois, report, altered)
            altered = copy.deepcopy(review)
            altered['events'][0]['field_reviews'] = {}
            with self.assertRaises(ValueError):
                bridge_activity_review(evidence, rois, report, altered)

    def test_reject_review_binding_changes(self):
        with tempfile.TemporaryDirectory() as d:
            evidence, rois, report = self.fixture(Path(d))
            review = self.approved(create_activity_review_template(evidence, rois, report))
            for key in ('ocr_report_sha256', 'evidence_manifest_sha256',
                        'recording_sha256', 'timestamp_semantics'):
                bad = copy.deepcopy(review)
                bad[key] = 'fake'
                with self.subTest(key=key), self.assertRaises(ValueError):
                    bridge_activity_review(evidence, rois, report, bad)

    def test_reject_duplicate_ocr_source(self):
        with tempfile.TemporaryDirectory() as d:
            evidence, rois, report = self.fixture(Path(d))
            bad = copy.deepcopy(report)
            bad['candidates'][1] = bad['candidates'][0]
            with self.assertRaises(ValueError):
                create_activity_review_template(evidence, rois, bad)

    def test_reject_unapproved_correction_without_reason(self):
        with tempfile.TemporaryDirectory() as d:
            evidence, rois, report = self.fixture(Path(d))
            review = self.approved(create_activity_review_template(evidence, rois, report))
            review['events'][0]['field_reviews']['pot']['approved_value'] = 41.5
            with self.assertRaisesRegex(ValueError, 'reason'):
                bridge_activity_review(evidence, rois, report, review)
            review['events'][0]['field_reviews']['pot']['correction_reason'] = 'Visually checked'
            result = bridge_activity_review(evidence, rois, report, review)
            self.assertEqual(result['observations'][0]['pot'], 41.5)
            self.assertTrue(result['provenance'][0]['evidence'][0]['corrected'])

    def test_file_workflow_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            evidence, rois, report = self.fixture(root)
            output = root / 'review.json'
            result = run_activity_review(evidence, rois, root/'ocr.json', output)
            self.assertEqual(result['analysis_status'], 'unapproved_activity_review_template')
            with self.assertRaises(FileExistsError):
                run_activity_review(evidence, rois, root/'ocr.json', output)
            approved = self.approved(result)
            (root/'approved.json').write_text(json.dumps(approved))
            checked = run_activity_review(evidence, rois, root/'ocr.json', root/'reviewed.json',
                                          human_review_path=root/'approved.json')
            self.assertEqual(checked['analysis_status'], 'human_reviewed_activity_observations')


if __name__ == '__main__':
    unittest.main()
