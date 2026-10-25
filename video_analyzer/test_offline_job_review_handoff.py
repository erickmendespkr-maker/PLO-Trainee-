"""Synthetic, fail-closed handoff tests. No poker footage or live integrations."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock

from offline_job_review_handoff import build_handoff, export_handoff, render_html
from offline_job_evidence_audit import PNG_SIGNATURE


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.job_id = 'b' * 32
        self.folder = self.root / 'results' / self.job_id
        (self.folder / 'table_01').mkdir(parents=True)
        self.video = self.root / 'recording.mp4'
        self.video.write_bytes(b'fake video bytes')
        self.image = self.folder / 'table_01/frame_00000.png'
        self.image.write_bytes(PNG_SIGNATURE + b'not real png for hash-only fixture')
        self.metadata = {'size_bytes': self.video.stat().st_size, 'duration_seconds': 3.,
                         'width': 320, 'height': 240}
        self.manifest = {'schema_version': 1, 'analysis_status': 'unverified_visual_evidence_only',
                         'recording': {'filename': self.video.name, **self.metadata},
                         'regions': [{'table_id': 1, 'x': 0, 'y': 0, 'width': 320, 'height': 240}],
                         'interval_seconds': 1., 'timestamp_semantics': 'nominal_sampling_grid_not_exact_source_pts',
                         'requires_manual_review': True,
                         'frames': [{'table_id': 1, 'nominal_timestamp_seconds': 0.,
                                     'image': 'table_01/frame_00000.png', 'status': 'unverified_visual_evidence'}]}
        self.result = {'schema_version': 1, 'job_id': self.job_id, 'status': 'review_required',
                       'requires_manual_review': True, 'frame_count': 1, 'table_count': 1,
                       'timestamp_semantics': 'nominal_sampling_grid_not_exact_source_pts',
                       'review_template': None, 'ocr_candidates': 0}
        self.job = {'job_id': self.job_id, 'state': 'review_required', 'source_path': str(self.video),
                    'source_sha256': hashlib.sha256(self.video.read_bytes()).hexdigest(),
                    'video_metadata': self.metadata, 'result_path': str(self.folder / 'result.json')}
        self.store = Mock()
        self.store.get.return_value = self.job
        self.write()

    def write(self):
        (self.folder / 'manifest.json').write_text(json.dumps(self.manifest), encoding='utf-8')
        (self.folder / 'result.json').write_text(json.dumps(self.result), encoding='utf-8')

    def build(self):
        return build_handoff(self.store, self.job_id, self.root / 'results')

    def ocr(self, *, text='Ks', field='hero_cards'):
        self.result['review_template'] = 'review_template.json'
        self.result['ocr_candidates'] = 1
        candidate = {'table_id': 1, 'timestamp': 0., 'field': field,
                     'status': 'candidate_unverified', 'source_image': 'table_01/frame_00000.png',
                     'parsed_candidate': text}
        (self.folder / 'ocr_candidates.json').write_text(json.dumps({
            'schema_version': 1, 'analysis_status': 'unverified_ocr_candidates_only',
            'requires_manual_review': True, 'candidates': [candidate]}), encoding='utf-8')
        self.template = {'schema_version': 1, 'analysis_status': 'unapproved_human_review_template',
                         'requires_manual_review': True,
                         'events': [{'table_id': 1, 'timestamp': 0., 'hand_id': None,
                                     'human_confirmed': False, 'field_reviews': {
                                         field: {'candidate_index': 0, 'human_confirmed': False,
                                                 'approved_value': None}}}]}
        self.write_template()
        self.write()

    def write_template(self):
        (self.folder / 'review_template.json').write_text(json.dumps(self.template), encoding='utf-8')

    def test_no_ocr_audited_handoff(self):
        report = self.build()
        self.assertEqual(report['frame_count'], 1)
        self.assertEqual(report['ocr_hint_count'], 0)
        self.assertFalse(report['ready_for_equity_or_ev'])
        self.assertFalse(report['automatic_clip_selection_authorized'])
        self.assertEqual(report['frames'][0]['sha256'], hashlib.sha256(self.image.read_bytes()).hexdigest())

    def test_unapproved_ocr_linked(self):
        self.ocr()
        report = self.build()
        self.assertEqual(report['ocr_hint_count'], 1)
        self.assertEqual(report['frames'][0]['ocr_hints_unverified'][0]['field'], 'hero_cards')
        self.assertFalse(report['hand_reconstruction_verified'])

    def test_export_creates_new_json_and_html(self):
        report = export_handoff(self.store, self.job_id, self.root / 'results')
        html = (self.folder / 'review_handoff/index.html').read_text(encoding='utf-8')
        self.assertIn('../table_01/frame_00000.png', html)
        self.assertIn('não verificado', html)
        self.assertEqual(json.loads((self.folder / 'review_handoff/review_handoff.json').read_text())['job_id'], self.job_id)
        with self.assertRaises(FileExistsError): export_handoff(self.store, self.job_id, self.root / 'results')
        self.assertEqual(report['frame_count'], 1)

    def test_export_leaves_queue_untouched(self):
        export_handoff(self.store, self.job_id, self.root / 'results')
        self.store.transition.assert_not_called()
        self.store.claim_next.assert_not_called()

    def test_reject_nominal_timestamp_tamper(self):
        self.manifest['frames'][0]['nominal_timestamp_seconds'] = 0.5
        self.write()
        with self.assertRaisesRegex(ValueError, 'Nonsequential'): self.build()

    def test_reject_frame_index_gap(self):
        self.manifest['frames'][0]['image'] = 'table_01/frame_00001.png'
        self.image.rename(self.folder / 'table_01/frame_00001.png')
        self.write()
        with self.assertRaisesRegex(ValueError, 'Nonsequential'): self.build()

    def test_reject_ocr_cross_table(self):
        self.ocr()
        p = self.folder / 'ocr_candidates.json'
        obj = json.loads(p.read_text())
        obj['candidates'][0]['table_id'] = 2
        p.write_text(json.dumps(obj))
        with self.assertRaisesRegex(ValueError, 'not bound'): self.build()

    def test_reject_ocr_wrong_source_image(self):
        self.ocr()
        p = self.folder / 'ocr_candidates.json'
        obj = json.loads(p.read_text())
        obj['candidates'][0]['source_image'] = 'table_01/frame_99999.png'
        p.write_text(json.dumps(obj))
        with self.assertRaisesRegex(ValueError, 'not bound'): self.build()

    def test_reject_ocr_wrong_timestamp(self):
        self.ocr()
        p = self.folder / 'ocr_candidates.json'
        obj = json.loads(p.read_text())
        obj['candidates'][0]['timestamp'] = 2
        p.write_text(json.dumps(obj))
        with self.assertRaisesRegex(ValueError, 'not bound'): self.build()

    def test_reject_template_preapproved(self):
        self.ocr()
        self.template['events'][0]['field_reviews']['hero_cards']['human_confirmed'] = True
        self.write_template()
        with self.assertRaisesRegex(ValueError, 'unapproved'): self.build()

    def test_reject_template_wrong_candidate(self):
        self.ocr()
        self.template['events'][0]['field_reviews']['hero_cards']['candidate_index'] = 9
        self.write_template()
        with self.assertRaisesRegex(ValueError, 'unapproved'): self.build()

    def test_reject_template_omits_field(self):
        self.ocr()
        self.template['events'] = []
        self.write_template()
        with self.assertRaisesRegex(ValueError, 'omits'): self.build()

    def test_reject_ocr_count_tamper(self):
        self.ocr()
        self.result['ocr_candidates'] = 2
        self.write()
        with self.assertRaisesRegex(ValueError, 'OCR report'): self.build()

    def test_reject_missing_ocr_template(self):
        self.result['ocr_candidates'] = 1
        self.write()
        with self.assertRaisesRegex(ValueError, 'without a review template'): self.build()

    def test_reject_mutated_source(self):
        self.video.write_bytes(b'changed')
        with self.assertRaises(ValueError): self.build()

    def test_reject_symlink_image(self):
        self.image.unlink()
        self.image.symlink_to(self.video)
        with self.assertRaises(ValueError): self.build()

    def test_escaping_and_bounded_html(self):
        self.ocr(text='<script>alert(1)</script>')
        report = self.build()
        html = render_html(report)
        self.assertNotIn('<script>', html)
        self.assertNotIn('alert(1)', html)
        # Preview remains bounded even for an unusually large validated report.
        item = report['frames'][0]
        report['frames'] = [dict(item, nominal_timestamp_seconds=float(i)) for i in range(200)]
        self.assertEqual(render_html(report).count('<figure>'), 120)

    def test_manifest_hash_detects_modified_png(self):
        self.manifest['frames'][0]['sha256'] = hashlib.sha256(self.image.read_bytes()).hexdigest()
        self.write()
        self.assertTrue(self.build()['manifest_frame_hashes_matched'])
        self.image.write_bytes(PNG_SIGNATURE + b'altered bytes')
        with self.assertRaisesRegex(ValueError, 'Frame SHA-256'): self.build()

    def test_worker_to_ocr_to_handoff_real_ffmpeg(self):
        from offline_jobs import OfflineJobStore
        from offline_worker import process_next
        self.video.unlink()
        subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error', '-f', 'lavfi',
                        '-i', 'testsrc2=size=320x240:rate=5:duration=3', '-an', '-c:v', 'mpeg4',
                        '-threads', '1', str(self.video)], check=True, timeout=30)
        roi = self.root / 'rois.json'
        roi.write_text(json.dumps({'tasks': [{'table_id': 1, 'field': 'pot',
            'region': {'x': 0, 'y': 0, 'width': 80, 'height': 50}}]}), encoding='utf-8')
        real_store = OfflineJobStore(self.root / 'jobs.sqlite')
        job = real_store.enqueue(self.video)
        processed = process_next(real_store, self.root / 'worker_results',
                                 interval_seconds=1, max_frames_per_table=3, roi_manifest=roi)
        self.assertEqual(processed['state'], 'review_required', processed['error'])
        report = export_handoff(real_store, job['job_id'], self.root / 'worker_results')
        self.assertEqual(report['frame_count'], 12)
        self.assertEqual(report['ocr_hint_count'], 3)
        self.assertFalse(report['ready_for_equity_or_ev'])
        self.assertTrue((self.root / 'worker_results' / job['job_id'] /
                         'review_handoff/index.html').exists())

    def test_ffmpeg_four_table_handoff(self):
        self.video.unlink()
        subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error', '-f', 'lavfi',
                        '-i', 'testsrc2=size=320x240:rate=5:duration=2', '-an', '-c:v', 'mpeg4',
                        '-threads', '1', str(self.video)], check=True, timeout=30)
        self.metadata['size_bytes'] = self.video.stat().st_size
        self.metadata['duration_seconds'] = 2.
        self.manifest['recording'] = {'filename': self.video.name, **self.metadata}
        self.job['source_sha256'] = hashlib.sha256(self.video.read_bytes()).hexdigest()
        self.manifest['regions'] = []
        self.manifest['frames'] = []
        for i, (x, y) in enumerate(((0, 0), (160, 0), (0, 120), (160, 120)), 1):
            self.manifest['regions'].append({'table_id': i, 'x': x, 'y': y, 'width': 160, 'height': 120})
            folder = self.folder / f'table_{i:02d}'
            folder.mkdir(exist_ok=True)
            image = folder / 'frame_00000.png'
            subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error', '-i', str(self.video),
                            '-vf', f'crop=160:120:{x}:{y}', '-frames:v', '1', '-update', '1', '-y', str(image)],
                           check=True, timeout=30)
            self.manifest['frames'].append({'table_id': i, 'nominal_timestamp_seconds': 0.,
                                            'image': f'table_{i:02d}/frame_00000.png',
                                            'status': 'unverified_visual_evidence'})
        self.result['frame_count'] = 4
        self.result['table_count'] = 4
        self.write()
        report = export_handoff(self.store, self.job_id, self.root / 'results')
        self.assertEqual(report['frame_count'], 4)
        self.assertEqual(report['table_frame_counts'], {'1': 1, '2': 1, '3': 1, '4': 1})
        self.assertTrue((self.folder / 'review_handoff/index.html').exists())


if __name__ == '__main__':
    unittest.main()
