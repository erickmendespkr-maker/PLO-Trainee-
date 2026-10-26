"""Synthetic tests for bounded PTS rebasing; no real poker or live input."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from offline_manual_clip_export import export_clip, video_stream_timing, digest_file
from offline_clip_decoded_pts_comparison import decoded_pts, _spacing


class TemporalRebaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.cfr = cls.root / 'cfr.mp4'
        cls.vfr = cls.root / 'vfr.mp4'
        cls.audio = cls.root / 'with_audio.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                        'testsrc2=size=160x120:rate=10:duration=5',
                        '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-y', str(cls.cfr)], check=True)
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                        'testsrc2=size=160x120:rate=10:duration=5',
                        '-vf', "select='not(mod(n,2))+not(mod(n,5))'",
                        '-fps_mode', 'vfr', '-c:v', 'libx264',
                        '-pix_fmt', 'yuv420p', '-y', str(cls.vfr)], check=True)
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                        'testsrc2=size=160x120:rate=10:duration=5',
                        '-f', 'lavfi', '-i', 'sine=frequency=440:duration=5',
                        '-map', '0:v', '-map', '1:a', '-c:v', 'libx264',
                        '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-y', str(cls.audio)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def selection(self, source, **overrides):
        obj = {'schema_version': 1, 'recording_sha256': digest_file(source),
               'table_id': 1, 'start_seconds': 0.55, 'end_seconds': 2.55,
               'human_selected': True, 'explanation': 'Synthetic video, not a poker hand',
               'reviewer_confidence': .7, 'crop': None}
        obj.update(overrides)
        return obj

    def export(self, source, tag, **overrides):
        sel = self.selection(source, **overrides)
        p = self.root / (tag + '_selection.json')
        p.write_text(json.dumps(sel), encoding='utf-8')
        clip = self.root / (tag + '.mp4')
        return clip, export_clip(source, p, clip)

    def test_cfr_non_frame_aligned_trim_starts_at_zero(self):
        clip, report = self.export(self.cfr, 'cfr_fix')
        timing = video_stream_timing(clip)
        self.assertAlmostEqual(timing['start_seconds'], 0, places=3)
        self.assertEqual(report['output_video_stream_start_pts_seconds'], 0)
        self.assertTrue(report['output_video_zero_based_stream_pts_verified'])
        self.assertFalse(report['frame_exact_export_verified'])
        self.assertAlmostEqual(report['output_video_stream_duration_seconds'], timing['duration_seconds'])
        self.assertGreaterEqual(report['output_video_duration_shortfall_seconds'], 0)
        self.assertLessEqual(report['output_video_duration_shortfall_seconds'], .25)
        self.assertFalse(report['source_pts_boundaries_verified'])
        self.assertFalse(report['strategic_error_established'])

    def test_vfr_spacing_is_not_force_converted_to_cfr(self):
        self.assertTrue(_spacing(decoded_pts(self.vfr, 0, 4))['variable_spacing_observed_in_sample'])
        clip, report = self.export(self.vfr, 'vfr_fix')
        self.assertAlmostEqual(video_stream_timing(clip)['start_seconds'], 0, places=3)
        self.assertTrue(_spacing(decoded_pts(clip, 0, 2.2))['variable_spacing_observed_in_sample'])
        self.assertFalse(report['frame_exact_export_verified'])

    def test_crop_and_zero_origin_together(self):
        crop = {'x': 0, 'y': 0, 'width': 80, 'height': 80}
        clip, report = self.export(self.cfr, 'crop_fix', crop=crop)
        meta = json.loads(subprocess.check_output(['ffprobe', '-v', 'error',
                '-select_streams', 'v:0', '-show_entries', 'stream=width,height,start_time',
                '-of', 'json', str(clip)]))['streams'][0]
        self.assertEqual((meta['width'], meta['height']), (80, 80))
        self.assertAlmostEqual(float(meta['start_time']), 0, places=3)
        self.assertEqual(report['selection']['crop'], crop)

    def test_audio_and_subtitle_preserved(self):
        clip, report = self.export(self.audio, 'audio_fix')
        streams = json.loads(subprocess.check_output(['ffprobe', '-v', 'error',
                '-show_entries', 'stream=codec_type', '-of', 'json', str(clip)]))['streams']
        self.assertEqual(sorted(s['codec_type'] for s in streams), ['audio', 'subtitle', 'video'])
        self.assertEqual(report['subtitle_track'], 'mov_text: human explanation')

    def test_four_manual_table_ids(self):
        for table_id in range(1, 5):
            with self.subTest(table_id=table_id):
                _, report = self.export(self.cfr, f'table_{table_id}', table_id=table_id)
                self.assertEqual(report['selection']['table_id'], table_id)
                self.assertFalse(report['automatic_clip_selection_authorized'])

    def test_export_is_no_overwrite(self):
        clip, _ = self.export(self.cfr, 'no_overwrite')
        before = hashlib.sha256(clip.read_bytes()).hexdigest()
        with self.assertRaises(ValueError):
            self.export(self.cfr, 'no_overwrite')
        self.assertEqual(before, hashlib.sha256(clip.read_bytes()).hexdigest())

    def test_output_sidecar_digest(self):
        clip, report = self.export(self.cfr, 'sidecar_fix')
        self.assertEqual(report['output_sha256'], digest_file(clip))
        self.assertEqual(json.loads(clip.with_suffix('.json').read_text()), report)

    def test_reject_nonzero_export_origin_without_publishing(self):
        with patch('offline_manual_clip_export.video_stream_timing', return_value={
            'start_seconds': .1, 'duration_seconds': 1.9}):
            with self.assertRaisesRegex(ValueError, 'nonzero initial PTS'):
                self.export(self.cfr, 'invalid_origin')
        self.assertFalse((self.root / 'invalid_origin.mp4').exists())

    def test_reject_large_video_duration_shortfall_without_publishing(self):
        with patch('offline_manual_clip_export.video_stream_timing', return_value={
            'start_seconds': 0, 'duration_seconds': 1.2}):
            with self.assertRaisesRegex(ValueError, 'video stream duration'):
                self.export(self.cfr, 'invalid_shortfall')
        self.assertFalse((self.root / 'invalid_shortfall.mp4').exists())

    def test_stream_timing_rejects_missing_start(self):
        from unittest.mock import Mock
        mock = Mock(stdout=b'{"streams":[{"duration":"2"}]}')
        with patch('offline_manual_clip_export._run', return_value=mock):
            with self.assertRaisesRegex(ValueError, 'Unknown video stream timing'):
                video_stream_timing(self.cfr)

    def test_stream_timing_rejects_nan(self):
        from unittest.mock import Mock
        mock = Mock(stdout=b'{"streams":[{"start_time":"NaN","duration":"2"}]}')
        with patch('offline_manual_clip_export._run', return_value=mock):
            with self.assertRaisesRegex(ValueError, 'Invalid video stream timing'):
                video_stream_timing(self.cfr)

    def test_stream_timing_rejects_ambiguous_streams(self):
        from unittest.mock import Mock
        mock = Mock(stdout=b'{"streams":[{},{}]}')
        with patch('offline_manual_clip_export._run', return_value=mock):
            with self.assertRaisesRegex(ValueError, 'Ambiguous video stream timing'):
                video_stream_timing(self.cfr)

    def test_stream_timing_rejects_oversized_metadata(self):
        from unittest.mock import Mock
        mock = Mock(stdout=b'x'*8192)
        with patch('offline_manual_clip_export._run', return_value=mock):
            with self.assertRaisesRegex(ValueError, 'Invalid video stream timing metadata'):
                video_stream_timing(self.cfr)


if __name__ == '__main__':
    unittest.main()
