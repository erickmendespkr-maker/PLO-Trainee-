"""Synthetic offline clip export tests (real FFmpeg/FFprobe, no poker accuracy claim)."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from PIL import Image, ImageDraw
from offline_reviewed_subtitled_batch_export import export, sha256


class ReviewedClipExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture_dir = tempfile.TemporaryDirectory()
        root = Path(cls.fixture_dir.name)
        image = Image.new('RGB', (640, 360), 'white')
        draw = ImageDraw.Draw(image)
        for i, color in enumerate(('red', 'green', 'blue', 'purple')):
            x, y = (i % 2) * 320, (i // 2) * 180
            draw.rectangle((x + 20, y + 20, x + 300, y + 160), fill=color)
        image.save(root / 'frame.png')
        cls.video = root / 'source.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-loop', '1',
                        '-i', str(root / 'frame.png'), '-t', '3', '-r', '12',
                        '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(cls.video)],
                       check=True, capture_output=True, timeout=45)

    @classmethod
    def tearDownClass(cls):
        cls.fixture_dir.cleanup()

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.manifest = self.root / 'review.json'
        self.output = self.root / 'output'
        self.data = {'schema_version': 1, 'time_basis': 'playback_seconds',
                     'recording_sha256': sha256(self.video),
                     'clips': [self.clip()]}
        self.write()

    @staticmethod
    def clip(**overrides):
        result = {'review_id': 'r1', 'table_id': 1, 'start_seconds': 0.4,
                  'end_seconds': 1.4, 'explanation': 'Decisao revisada: conferir pote',
                  'human_reviewed': True}
        result.update(overrides)
        return result

    def write(self):
        self.manifest.write_text(json.dumps(self.data), encoding='utf-8')

    def test_real_mp4_with_visible_subtitle_and_hash(self):
        result = export(self.video, self.manifest, self.output)
        clip = result['clips'][0]
        self.assertTrue((self.output / clip['mp4']).is_file())
        self.assertEqual(sha256(self.output / clip['mp4']), clip['mp4_sha256'])
        self.assertIn('Decisao revisada', (self.output / clip['srt']).read_text())
        self.assertAlmostEqual(clip['output_duration_seconds'], 1, delta=0.6)
        self.assertFalse(result['review_authenticity_verified'])
        self.assertFalse(result['equity_or_ev_verified'])

    def test_four_table_clips(self):
        self.data['clips'] = [self.clip(review_id=f'r{i}', table_id=i,
                                        start_seconds=0.2, end_seconds=0.9)
                              for i in range(1, 5)]
        self.write()
        report = export(self.video, self.manifest, self.output)
        self.assertEqual(len(report['clips']), 4)
        self.assertEqual(len(list(self.output.glob('*.mp4'))), 4)

    def test_ambiguous_pts_basis_rejected(self):
        self.data['time_basis'] = 'source_pts_seconds'
        self.write()
        with self.assertRaisesRegex(ValueError, 'manifest/source'):
            export(self.video, self.manifest, self.output)

    def test_duplicate_id_rejected(self):
        self.data['clips'] *= 2
        self.write()
        with self.assertRaisesRegex(ValueError, 'duplicate review ID'):
            export(self.video, self.manifest, self.output)
        self.assertFalse(self.output.exists())

    def test_unreviewed_rejected(self):
        self.data['clips'][0]['human_reviewed'] = False
        self.write()
        with self.assertRaisesRegex(ValueError, 'human review required'):
            export(self.video, self.manifest, self.output)

    def test_wrong_video_hash_rejected(self):
        self.data['recording_sha256'] = '0' * 64
        self.write()
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            export(self.video, self.manifest, self.output)

    def test_interval_outside_video_rejected(self):
        self.data['clips'][0]['end_seconds'] = 30
        self.write()
        with self.assertRaisesRegex(ValueError, 'interval'):
            export(self.video, self.manifest, self.output)

    def test_subtitle_injection_rejected(self):
        self.data['clips'][0]['explanation'] = '{\\an8}spoof'
        self.write()
        with self.assertRaisesRegex(ValueError, 'subtitle'):
            export(self.video, self.manifest, self.output)

    def test_create_only(self):
        export(self.video, self.manifest, self.output)
        before = sha256(self.output / 'export_report.json')
        with self.assertRaisesRegex(ValueError, 'new, disjoint'):
            export(self.video, self.manifest, self.output)
        self.assertEqual(sha256(self.output / 'export_report.json'), before)

    def test_duplicate_json_keys_rejected(self):
        self.manifest.write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaisesRegex(ValueError, 'duplicate JSON key'):
            export(self.video, self.manifest, self.output)

    def test_failure_does_not_publish(self):
        with self.assertRaisesRegex(ValueError, 'media tool failed'):
            export(self.video, self.manifest, self.output, ffmpeg='missing_ffmpeg_xyz')
        self.assertFalse(self.output.exists())

    def test_symlink_input_rejected(self):
        alias = self.root / 'alias.mp4'
        alias.symlink_to(self.video)
        with self.assertRaisesRegex(ValueError, 'unsafe input'):
            export(alias, self.manifest, self.output)


if __name__ == '__main__':
    unittest.main()
