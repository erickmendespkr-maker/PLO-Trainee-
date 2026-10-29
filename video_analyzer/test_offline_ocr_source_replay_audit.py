"""Offline FFmpeg/Tesseract synthetic tests for exact source -> frame -> ROI replay."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from offline_video_ingest_probe import build
from offline_sampled_visual_change import analyze
from offline_adaptive_change_refinement import refine
from offline_refined_roi_ocr import scan
from offline_ocr_source_replay_audit import audit


class OcrSourceReplayAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.video = cls.root / 'video.mp4'
        subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi',
                        '-i', 'color=c=gray:s=320x180:r=1', '-t', '6',
                        '-vf', "drawbox=x=0:y=0:w=320:h=180:color=white:t=fill:enable='gte(t,2)'",
                        '-c:v', 'mpeg4', '-y', str(cls.video)],
                       check=True, capture_output=True, timeout=60)
        cls.regions = cls.root / 'regions.json'
        cls.regions.write_text(json.dumps({'tables': [
            {'table_id': 1, 'x': 0, 'y': 0, 'width': 320, 'height': 180}]}))
        cls.ingest = cls.root / 'ingest'
        build(cls.video, cls.regions, cls.ingest)
        cls.change_dir = cls.root / 'changes'
        analyze(cls.ingest, cls.change_dir)
        cls.changes = cls.change_dir / 'visual_changes.json'
        cls.refined = cls.root / 'refined'
        refine(cls.video, cls.regions, cls.ingest, cls.changes, cls.refined)
        dense = json.loads((cls.refined / 'dense_refinement.json').read_text())
        cls.dense_frame = dense['refinements'][0]['new_frames'][0]['file']
        cls.sparse_frame = json.loads((cls.ingest / 'manifest.json').read_text())['samples'][0]['file']
        cls.manifest_sha = cls.sha(cls.ingest / 'manifest.json')
        cls.dense_sha = cls.sha(cls.refined / 'dense_refinement.json')

    @staticmethod
    def sha(path):
        import hashlib
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.temp_case = tempfile.TemporaryDirectory()
        self.case = Path(self.temp_case.name)
        self.tasks = self.case / 'tasks.json'
        self.ocr = self.case / 'ocr'
        self.task_data = {
            'schema_version': 1,
            'source_ingest_manifest_sha256': self.manifest_sha,
            'source_dense_refinement_sha256': self.dense_sha,
            'tasks': [
                {'table_id': 1, 'frame_file': self.sparse_frame, 'field': 'pot',
                 'roi': {'x': 1, 'y': 1, 'width': 101, 'height': 39}},
                {'table_id': 1, 'frame_file': self.dense_frame, 'field': 'board',
                 'roi': {'x': 4, 'y': 8, 'width': 120, 'height': 60}}
            ]}
        self.save_tasks()
        scan(self.video, self.regions, self.ingest, self.changes, self.refined,
             self.tasks, self.ocr)

    def tearDown(self):
        self.temp_case.cleanup()

    def save_tasks(self):
        self.tasks.write_text(json.dumps(self.task_data), 'utf-8')

    def audit(self, **kwargs):
        args = {'video': self.video, 'regions_json': self.regions,
                'ingest_dir': self.ingest, 'changes_json': self.changes,
                'refined_dir': self.refined, 'tasks_json': self.tasks,
                'ocr_dir': self.ocr}
        args.update(kwargs)
        return audit(**args)

    def test_exact_replay_sparse_dense_and_odd_roi(self):
        result = self.audit()
        self.assertEqual(result['source_frames_replayed_exactly'], 2)
        self.assertEqual(result['roi_pngs_replayed_exactly'], 2)
        self.assertTrue(result['source_video_to_frame_to_roi_reproduced'])
        self.assertFalse(result['ready_for_equity_or_ev'])
        self.assertFalse(result['ocr_semantics_verified'])
        self.assertEqual(result['source_video_sha256'], self.sha(self.video))

    def test_replay_is_read_only(self):
        files = [self.video, self.regions, self.tasks,
                 self.ocr / 'roi_ocr_proposals.json', self.ocr / 'roi_000.png',
                 self.ingest / 'manifest.json']
        before = [self.sha(p) for p in files]
        self.audit()
        self.assertEqual(before, [self.sha(p) for p in files])

    def test_source_video_hash_mismatch(self):
        altered = self.case / 'altered.mp4'
        shutil.copyfile(self.video, altered)
        with altered.open('ab') as stream:
            stream.write(b'altered')
        with self.assertRaisesRegex(ValueError, 'source video'):
            self.audit(video=altered)

    def test_changed_regions_rejected(self):
        changed = self.case / 'changed_regions.json'
        changed.write_text(self.regions.read_text().replace('320', '318'))
        with self.assertRaisesRegex(ValueError, 'region'):
            self.audit(regions_json=changed)

    def test_tasks_hash_mismatch(self):
        self.task_data['tasks'][0]['roi']['x'] = 2
        self.save_tasks()
        with self.assertRaisesRegex(ValueError, 'provenance'):
            self.audit()

    def test_duplicate_task_key_rejected(self):
        self.tasks.write_text(self.tasks.read_text().replace(
            '"schema_version": 1', '"schema_version": 1, "schema_version": 1'))
        with self.assertRaises(ValueError):
            self.audit()

    def test_nonfinite_task_rejected(self):
        self.tasks.write_text(self.tasks.read_text().replace('"x": 1', '"x": NaN'))
        with self.assertRaises(ValueError):
            self.audit()

    def test_ocr_report_false_equity_claim_rejected(self):
        p = self.ocr / 'roi_ocr_proposals.json'
        data = json.loads(p.read_text())
        data['ready_for_equity_or_ev'] = True
        p.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'analysis status'):
            self.audit()

    def test_roi_png_modified_rejected(self):
        (self.ocr / 'roi_000.png').write_bytes(b'bad')
        with self.assertRaisesRegex(ValueError, 'ROI PNG'):
            self.audit()

    def test_roi_png_rehashed_forgery_rejected_by_replay(self):
        # Hash checks alone would accept this modified PNG + updated OCR report.
        png = self.ocr / 'roi_000.png'
        png.write_bytes((self.ocr / 'roi_001.png').read_bytes())
        report = self.ocr / 'roi_ocr_proposals.json'
        data = json.loads(report.read_text())
        data['proposals'][0]['roi_png_sha256'] = self.sha(png)
        report.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'ROI PNG replay mismatch'):
            self.audit()

    def test_roi_symlink_rejected(self):
        target = self.case / 'other.png'
        shutil.copyfile(self.ocr / 'roi_000.png', target)
        (self.ocr / 'roi_000.png').unlink()
        (self.ocr / 'roi_000.png').symlink_to(target)
        with self.assertRaisesRegex(ValueError, 'ROI PNG'):
            self.audit()

    def test_wrong_ocr_frame_sha_rejected(self):
        p = self.ocr / 'roi_ocr_proposals.json'
        data = json.loads(p.read_text())
        data['proposals'][0]['source_frame_sha256'] = '0' * 64
        p.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'identity'):
            self.audit()

    def test_ocr_frame_pts_forgery_rejected(self):
        p = self.ocr / 'roi_ocr_proposals.json'
        data = json.loads(p.read_text())
        data['proposals'][0]['decoded_source_pts_seconds'] += 1
        p.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'identity'):
            self.audit()

    def test_replayed_frame_mismatch_rejected(self):
        original = __import__('offline_ocr_source_replay_audit').extract_sample_frame
        def altered(*args, **kwargs):
            result = original(*args, **kwargs)
            Path(args[3]).write_bytes(b'fake frame')
            return result
        with patch('offline_ocr_source_replay_audit.extract_sample_frame', side_effect=altered):
            with self.assertRaisesRegex(ValueError, 'JPEG mismatch'):
                self.audit()

    def test_replayed_pts_mismatch_rejected(self):
        original = __import__('offline_ocr_source_replay_audit').extract_sample_frame
        def altered(*args, **kwargs):
            result = original(*args, **kwargs)
            result['actual_frame_timestamp_seconds'] += 1
            return result
        with patch('offline_ocr_source_replay_audit.extract_sample_frame', side_effect=altered):
            with self.assertRaisesRegex(ValueError, 'PTS mismatch'):
                self.audit()

    def test_replayed_roi_mismatch_rejected(self):
        with patch('offline_ocr_source_replay_audit.replay_roi', side_effect=lambda a,b,c: Path(c).write_bytes(b'fake roi')):
            with self.assertRaisesRegex(ValueError, 'ROI PNG replay mismatch'):
                self.audit()

    def test_invalid_ocr_proposal_status_rejected(self):
        p = self.ocr / 'roi_ocr_proposals.json'
        data = json.loads(p.read_text())
        data['proposals'][0]['status'] = 'verified'
        p.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'promoted'):
            self.audit()

    def test_invalid_roi_outside_table_rejected(self):
        p = self.ocr / 'roi_ocr_proposals.json'
        data = json.loads(p.read_text())
        self.task_data['tasks'][0]['roi']['x'] = 300
        self.save_tasks()
        data['source_roi_tasks_sha256'] = self.sha(self.tasks)
        data['proposals'][0]['roi']['x'] = 300
        p.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'outside table'):
            self.audit()


if __name__ == '__main__':
    unittest.main()
