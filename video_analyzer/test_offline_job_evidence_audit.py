"""Synthetic tests for read-only worker-evidence integrity handoff."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from offline_job_evidence_audit import audit_job, PNG_SIGNATURE


class EvidenceAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.job_id = 'a' * 32
        self.directory = self.root / 'results' / self.job_id
        (self.directory / 'table_01').mkdir(parents=True)
        self.video = self.root / 'sample.mp4'
        self.video.write_bytes(b'fictional video')
        self.image = self.directory / 'table_01' / 'frame_00000.png'
        self.image.write_bytes(PNG_SIGNATURE + b'synthetic pixels')
        self.meta = {'size_bytes': self.video.stat().st_size, 'duration_seconds': 5.0,
                     'width': 320, 'height': 240}
        self.manifest = {'schema_version': 1, 'analysis_status': 'unverified_visual_evidence_only',
                         'recording': {'filename': self.video.name, **self.meta},
                         'regions': [{'table_id': 1, 'x': 0, 'y': 0, 'width': 320, 'height': 240}],
                         'interval_seconds': 1.0, 'timestamp_semantics': 'nominal_sampling_grid_not_exact_source_pts',
                         'requires_manual_review': True,
                         'frames': [{'table_id': 1, 'nominal_timestamp_seconds': 0.0,
                                     'image': 'table_01/frame_00000.png', 'status': 'unverified_visual_evidence'}]}
        self.result = {'schema_version': 1, 'job_id': self.job_id, 'status': 'review_required',
                       'requires_manual_review': True, 'frame_count': 1, 'table_count': 1,
                       'timestamp_semantics': 'nominal_sampling_grid_not_exact_source_pts',
                       'review_template': None}
        self.job = {'job_id': self.job_id, 'state': 'review_required',
                    'source_path': str(self.video), 'source_sha256': hashlib.sha256(self.video.read_bytes()).hexdigest(),
                    'video_metadata': self.meta, 'result_path': str(self.directory / 'result.json')}
        self.store = Mock()
        self.store.get.return_value = self.job
        self.write()

    def write(self):
        (self.directory / 'manifest.json').write_text(json.dumps(self.manifest), encoding='utf-8')
        (self.directory / 'result.json').write_text(json.dumps(self.result), encoding='utf-8')

    def audit(self):
        return audit_job(self.store, self.job_id, self.root / 'results')

    def test_valid_unverified_packet(self):
        packet = self.audit()
        self.assertEqual(packet['frame_count'], 1)
        self.assertFalse(packet['hand_reconstruction_verified'])
        self.assertFalse(packet['ready_for_equity_or_ev'])
        self.assertEqual(packet['frames'][0]['sha256'], hashlib.sha256(self.image.read_bytes()).hexdigest())

    def test_queue_not_modified(self):
        self.audit()
        self.store.get.assert_called_once_with(self.job_id)
        self.assertFalse((self.directory / 'audit.json').exists())

    def test_reject_job_not_reviewed(self):
        self.job['state'] = 'completed'
        with self.assertRaises(ValueError): self.audit()

    def test_reject_source_mutation(self):
        self.video.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'SHA-256'): self.audit()

    def test_reject_result_path_escape(self):
        self.job['result_path'] = str(self.root / 'other.json')
        with self.assertRaises(ValueError): self.audit()

    def test_reject_cross_table_image(self):
        self.manifest['frames'][0]['table_id'] = 2
        self.write()
        with self.assertRaises(ValueError): self.audit()

    def test_reject_traversal(self):
        self.manifest['frames'][0]['image'] = '../secrets.png'
        self.write()
        with self.assertRaises(ValueError): self.audit()

    def test_reject_duplicate_frames(self):
        self.manifest['frames'].append(copy.deepcopy(self.manifest['frames'][0]))
        self.result['frame_count'] = 2
        self.write()
        with self.assertRaises(ValueError): self.audit()

    def test_reject_frame_count_tamper(self):
        self.result['frame_count'] = 99
        self.write()
        with self.assertRaises(ValueError): self.audit()

    def test_reject_false_review_flag(self):
        self.manifest['requires_manual_review'] = False
        self.write()
        with self.assertRaises(ValueError): self.audit()

    def test_reject_nonfinite_time(self):
        self.manifest['frames'][0]['nominal_timestamp_seconds'] = float('nan')
        self.write()
        with self.assertRaises(ValueError): self.audit()

    def test_reject_image_symlink(self):
        self.image.unlink()
        self.image.symlink_to(self.video)
        with self.assertRaises(ValueError): self.audit()

    def test_reject_invalid_png(self):
        self.image.write_bytes(b'not a png')
        with self.assertRaises(ValueError): self.audit()

    def test_reject_symlinked_table_directory(self):
        self.image.unlink()
        (self.directory / 'table_01').rmdir()
        external = self.root / 'external'
        external.mkdir()
        (external / 'frame_00000.png').write_bytes(PNG_SIGNATURE + b'pixels')
        (self.directory / 'table_01').symlink_to(external, target_is_directory=True)
        with self.assertRaises(ValueError): self.audit()

    def test_reject_unexpected_review_template(self):
        self.result['review_template'] = '../template.json'
        self.write()
        with self.assertRaises(ValueError): self.audit()

    def test_reject_region_outside_video(self):
        self.manifest['regions'][0]['width'] = 321
        self.write()
        with self.assertRaises(ValueError): self.audit()

    def test_reject_job_id_format(self):
        with self.assertRaises(ValueError): audit_job(self.store, '../bad', self.root / 'results')

    def test_real_ffmpeg_four_table_frames(self):
        import subprocess
        self.video.unlink()
        subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
                        '-f', 'lavfi', '-i', 'testsrc2=size=320x240:rate=5:duration=2',
                        '-an', '-c:v', 'mpeg4', '-threads', '1', str(self.video)],
                       check=True, timeout=30)
        self.meta['size_bytes'] = self.video.stat().st_size
        self.meta['duration_seconds'] = 2.0
        self.manifest['recording'] = {'filename': self.video.name, **self.meta}
        self.job['source_sha256'] = hashlib.sha256(self.video.read_bytes()).hexdigest()
        self.manifest['regions'] = []
        self.manifest['frames'] = []
        for table_id, (x, y) in enumerate(((0, 0), (160, 0), (0, 120), (160, 120)), 1):
            self.manifest['regions'].append({'table_id': table_id, 'x': x, 'y': y,
                                             'width': 160, 'height': 120})
            folder = self.directory / f'table_{table_id:02d}'
            folder.mkdir(exist_ok=True)
            image = folder / 'frame_00000.png'
            subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
                            '-i', str(self.video), '-vf', f'crop=160:120:{x}:{y}',
                            '-frames:v', '1', '-update', '1', '-y', str(image)],
                           check=True, timeout=30)
            self.manifest['frames'].append({'table_id': table_id,
                'nominal_timestamp_seconds': 0.0,
                'image': f'table_{table_id:02d}/frame_00000.png',
                'status': 'unverified_visual_evidence'})
        self.result['frame_count'] = 4
        self.result['table_count'] = 4
        self.write()
        packet = self.audit()
        self.assertEqual(packet['frame_count'], 4)
        self.assertEqual(packet['table_frame_counts'], {'1': 1, '2': 1, '3': 1, '4': 1})
        self.assertTrue(all(item['verification'] == 'bytes_only_not_visual_truth'
                            for item in packet['frames']))

    def test_reject_oversized_image(self):
        with self.image.open('ab') as stream:
            stream.truncate(30 * 1024 * 1024 + 1)
        with self.assertRaises(ValueError): self.audit()


if __name__ == '__main__':
    unittest.main()
