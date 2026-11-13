"""Real FFmpeg integration checks for source/clip PTS alignment (synthetic only)."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from offline_source_pts_alignment import compare_frame_timelines


def pts(path):
    result = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
        '-show_entries', 'frame=best_effort_timestamp_time', '-of', 'json', str(path)],
        check=True, capture_output=True, text=True)
    return [float(f['best_effort_timestamp_time']) for f in json.loads(result.stdout)['frames']]


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg tools required')
class FFmpegAlignmentIntegration(unittest.TestCase):
    def test_transcoded_clip_matches_source_timeline(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'source.mp4'
            clip = Path(directory) / 'clip.mp4'
            subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-f', 'lavfi',
                '-i', 'testsrc2=size=160x90:rate=10:duration=5', '-c:v', 'mpeg4',
                '-q:v', '3', '-y', str(source)], check=True)
            subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-ss', '1',
                '-i', str(source), '-t', '2', '-an', '-c:v', 'mpeg4', '-q:v', '3',
                '-y', str(clip)], check=True)
            source_pts, clip_pts = pts(source), pts(clip)
            self.assertEqual(len(clip_pts), 20)
            result = compare_frame_timelines(source_pts, clip_pts, 1, 3, tolerance_seconds=0.06)
            self.assertEqual(result['status'], 'FRAME_TIMING_CANDIDATE_ONLY')
            self.assertFalse(result['approved_for_publication'])
            self.assertFalse(result['visual_hand_verified'])
            with self.assertRaises(ValueError):
                compare_frame_timelines(source_pts, clip_pts, 3.5, 5, tolerance_seconds=0.01)


if __name__ == '__main__':
    unittest.main()
