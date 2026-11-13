import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from offline_clip_pts_audit import audit_decoded_pts


class PtsAuditTests(unittest.TestCase):
    def test_real_synthetic_mp4(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'synthetic.mp4'
            subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi', '-i',
                            'testsrc2=size=96x64:rate=10:duration=2', '-c:v', 'mpeg4',
                            '-y', str(path)], check=True)
            result = audit_decoded_pts(path)
            self.assertEqual(result['frame_count'], 20)
            self.assertEqual(result['status'], 'DECODED_PTS_MONOTONIC_ONLY')
            self.assertFalse(result['source_timeline_verified'])
            self.assertFalse(result['approved_for_publication'])

    def test_missing_file(self):
        with self.assertRaises(ValueError):
            audit_decoded_pts('/nonexistent/video.mp4')

    def test_invalid_limit(self):
        with self.assertRaises(ValueError):
            audit_decoded_pts(__file__, max_frames=True)

    def test_symlink(self):
        with tempfile.TemporaryDirectory() as folder:
            link = Path(folder) / 'link.mp4'
            link.symlink_to(__file__)
            with self.assertRaises(ValueError):
                audit_decoded_pts(link)

    def test_non_video(self):
        with self.assertRaises(ValueError):
            audit_decoded_pts(__file__)

    def test_duplicate_pts(self):
        with patch('offline_clip_pts_audit.subprocess.run') as run:
            run.return_value.stdout = json.dumps({'frames': [
                {'best_effort_timestamp_time': '0.0'},
                {'best_effort_timestamp_time': '0.0'}]})
            with self.assertRaisesRegex(ValueError, 'non-increasing'):
                audit_decoded_pts(__file__)

    def test_missing_pts(self):
        with patch('offline_clip_pts_audit.subprocess.run') as run:
            run.return_value.stdout = json.dumps({'frames': [{}]})
            with self.assertRaisesRegex(ValueError, 'missing'):
                audit_decoded_pts(__file__)

    def test_nonfinite_pts(self):
        with patch('offline_clip_pts_audit.subprocess.run') as run:
            run.return_value.stdout = json.dumps({'frames': [{'best_effort_timestamp_time': 'NaN'}]})
            with self.assertRaisesRegex(ValueError, 'nonfinite'):
                audit_decoded_pts(__file__)

    def test_excessive_frames(self):
        with patch('offline_clip_pts_audit.subprocess.run') as run:
            run.return_value.stdout = json.dumps({'frames': [{}, {}]})
            with self.assertRaisesRegex(ValueError, 'excessive'):
                audit_decoded_pts(__file__, max_frames=1)


if __name__ == '__main__':
    unittest.main()
