"""Regression tests for offline MP4/JSON sidecar handoff."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    from . import offline_review_bundle_export as module
except ImportError:
    import offline_review_bundle_export as module


class ReviewBundleExportTests(unittest.TestCase):
    def make_video(self, path):
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                        'color=c=black:s=160x90:r=10:d=3',
                        '-c:v', 'libx264', str(path)], check=True)

    def test_mp4_json_sidecar_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'source.mp4'
            target = Path(folder) / 'clip.mp4'
            self.make_video(source)
            analysis = {'start_s': 0.5, 'end_s': 1.5, 'status': 'INSUFFICIENT_DATA',
                        'evidence': {'status': 'INSUFFICIENT_DATA'}}
            result = module.export_review_bundle(source, target, analysis,
                                                 clip_start_s=0.5, clip_end_s=1.5)
            self.assertTrue(target.is_file())
            report = json.loads(target.with_suffix('.json').read_text(encoding='utf-8'))
            self.assertEqual(result['status'], 'INSUFFICIENT_DATA')
            self.assertFalse(report['clip']['visually_verified'])
            self.assertEqual(len(report['clip']['sha256']), 64)
            with self.assertRaises(FileExistsError):
                module.export_review_bundle(source, target, analysis,
                                            clip_start_s=0.5, clip_end_s=1.5)

    def test_misaligned_hand_does_not_export(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'source.mp4'
            target = Path(folder) / 'clip.mp4'
            self.make_video(source)
            analysis = {'start_s': 0.5, 'end_s': 2.5, 'status': 'INSUFFICIENT_DATA',
                        'evidence': {'status': 'INSUFFICIENT_DATA'}}
            with self.assertRaises(ValueError):
                module.export_review_bundle(source, target, analysis,
                                            clip_start_s=0.5, clip_end_s=1.5)
            self.assertFalse(target.exists())
            self.assertFalse(target.with_suffix('.json').exists())


if __name__ == '__main__':
    unittest.main()
