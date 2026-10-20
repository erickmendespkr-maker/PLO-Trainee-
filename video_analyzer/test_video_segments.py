import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from video_segments import extract_clip, sample_frames


class VideoSegmentsTests(unittest.TestCase):
    def test_sampling_interval_rejects_zero(self):
        with self.assertRaises(ValueError):
            sample_frames('video.mp4', '/tmp/unused', 0)

    def test_clip_rejects_negative_start(self):
        with self.assertRaises(ValueError):
            extract_clip('video.mp4', 'clip.mp4', -1, 10)

    def test_clip_rejects_reversed_timestamps(self):
        with self.assertRaises(ValueError):
            extract_clip('video.mp4', 'clip.mp4', 12, 8)

    def test_clip_invokes_ffmpeg_with_duration(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'clip.mp4'
            with patch('video_segments._run') as runner:
                extract_clip('input.mp4', output, 12, 17)
                cmd = runner.call_args.args[0]
                self.assertEqual(cmd[cmd.index('-t') + 1], '5')
                self.assertEqual(cmd[cmd.index('-ss') + 1], '12')
                self.assertIn('-nostdin', cmd)


if __name__ == '__main__':
    unittest.main()
