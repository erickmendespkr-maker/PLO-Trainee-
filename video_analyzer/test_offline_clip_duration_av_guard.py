"""CFR/VFR duration guard and A/V stream-metadata tests using synthetic recordings.

No real poker footage, OCR assertions, frame-identity proof or content-sync claims.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from offline_manual_clip_export import (audio_stream_timing, digest_file,
                                        export_clip, video_stream_timing)
from offline_clip_decoded_pts_comparison import decoded_pts, _spacing


class DurationAvGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.cfr = cls.root / 'cfr.mp4'
        cls.vfr = cls.root / 'vfr.mp4'
        cls.av = cls.root / 'av.mp4'
        cls.fps30 = cls.root / 'fps30.mp4'
        for source, rate in ((cls.cfr, 10), (cls.fps30, 30)):
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                            f'testsrc2=size=160x120:rate={rate}:duration=5',
                            '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-y', str(source)],
                           check=True)
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                        'testsrc2=size=160x120:rate=10:duration=5',
                        '-vf', "select='not(mod(n,2))+not(mod(n,5))'",
                        '-fps_mode', 'vfr', '-c:v', 'libx264',
                        '-pix_fmt', 'yuv420p', '-y', str(cls.vfr)], check=True)
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                        'testsrc2=size=160x120:rate=10:duration=5',
                        '-f', 'lavfi', '-i', 'sine=frequency=440:duration=5',
                        '-map', '0:v', '-map', '1:a', '-c:v', 'libx264',
                        '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-y', str(cls.av)],
                       check=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def export(self, source, name, start=0.55, end=2.55, crop=None):
        selection = {'schema_version': 1, 'recording_sha256': digest_file(source),
                     'table_id': 2, 'start_seconds': start, 'end_seconds': end,
                     'human_selected': True, 'explanation': 'Revisão de vídeo sintético',
                     'reviewer_confidence': 0.6, 'crop': crop}
        selection_path = self.root / (name + '_selection.json')
        selection_path.write_text(json.dumps(selection), encoding='utf-8')
        clip_path = self.root / (name + '.mp4')
        report = export_clip(source, selection_path, clip_path)
        return clip_path, report

    @staticmethod
    def decoded_count(path):
        raw = subprocess.check_output(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
                                       '-count_frames', '-show_entries',
                                       'stream=nb_read_frames', '-of', 'json', str(path)])
        return int(json.loads(raw)['streams'][0]['nb_read_frames'])

    def test_10fps_non_aligned_window_has_20_decoded_frames(self):
        clip, report = self.export(self.cfr, 'nonaligned')
        self.assertEqual(self.decoded_count(clip), 20)
        self.assertAlmostEqual(video_stream_timing(clip)['duration_seconds'], 2, places=3)
        self.assertEqual(report['output_video_duration_shortfall_seconds'], 0)
        self.assertEqual(report['output_trim_end_guard_seconds'], .001)
        self.assertFalse(report['frame_exact_export_verified'])

    def test_10fps_aligned_window_has_20_decoded_frames(self):
        clip, report = self.export(self.cfr, 'aligned', start=.5, end=2.5)
        self.assertEqual(self.decoded_count(clip), 20)
        self.assertAlmostEqual(report['output_video_stream_duration_seconds'], 2, places=3)

    def test_30fps_window_has_60_decoded_frames(self):
        clip, report = self.export(self.fps30, 'fps30_cut')
        self.assertEqual(self.decoded_count(clip), 60)
        self.assertAlmostEqual(report['output_video_stream_duration_seconds'], 2, places=3)

    def test_eof_shortfall_is_disclosed_not_filled(self):
        clip, report = self.export(self.cfr, 'eof', start=3.0, end=5.0)
        self.assertEqual(self.decoded_count(clip), 19)
        self.assertGreaterEqual(report['output_video_duration_shortfall_seconds'], .09)
        self.assertFalse(report['frame_exact_export_verified'])

    def test_vfr_spacing_stays_variable(self):
        clip, report = self.export(self.vfr, 'vfr_cut')
        self.assertTrue(_spacing(decoded_pts(clip, 0, 2.2))['variable_spacing_observed_in_sample'])
        self.assertFalse(report['source_pts_boundaries_verified'])

    def test_audio_stream_metadata_and_no_content_sync_claim(self):
        clip, report = self.export(self.av, 'av_cut')
        self.assertTrue(report['output_audio_present'])
        self.assertIsNotNone(audio_stream_timing(clip))
        self.assertAlmostEqual(report['output_audio_minus_video_start_seconds'], 0, delta=.05)
        self.assertLess(abs(report['output_audio_minus_video_end_seconds']), .1)
        self.assertFalse(report['audio_video_content_sync_verified'])

    def test_silent_clip_has_explicit_null_audio_metadata(self):
        _, report = self.export(self.cfr, 'silent_cut')
        self.assertFalse(report['output_audio_present'])
        self.assertIsNone(report['output_audio_stream_timing'])
        self.assertIsNone(report['output_audio_minus_video_start_seconds'])
        self.assertIsNone(report['output_audio_minus_video_end_seconds'])

    def test_crop_still_valid(self):
        clip, report = self.export(self.cfr, 'crop', crop={'x': 0, 'y': 0,
                                                        'width': 80, 'height': 80})
        self.assertEqual(report['selection']['crop']['width'], 80)
        self.assertEqual(self.decoded_count(clip), 20)

    def test_no_overwrite_after_success(self):
        clip, _ = self.export(self.cfr, 'no_overwrite')
        old = hashlib.sha256(clip.read_bytes()).hexdigest()
        with self.assertRaises(ValueError):
            self.export(self.cfr, 'no_overwrite')
        self.assertEqual(hashlib.sha256(clip.read_bytes()).hexdigest(), old)

    def test_audio_probe_rejects_malformed_json(self):
        with patch('offline_manual_clip_export._run', return_value=Mock(stdout=b'broken')):
            with self.assertRaises(ValueError):
                audio_stream_timing(self.av)

    def test_audio_probe_rejects_two_audio_streams(self):
        raw = b'{"streams":[{"start_time":"0","duration":"2"},{"start_time":"0","duration":"2"}]}'
        with patch('offline_manual_clip_export._run', return_value=Mock(stdout=raw)):
            with self.assertRaisesRegex(ValueError, 'Ambiguous audio'):
                audio_stream_timing(self.av)

    def test_audio_probe_rejects_nan_duration(self):
        raw = b'{"streams":[{"start_time":"0","duration":"NaN"}]}'
        with patch('offline_manual_clip_export._run', return_value=Mock(stdout=raw)):
            with self.assertRaisesRegex(ValueError, 'Invalid audio'):
                audio_stream_timing(self.av)


if __name__ == '__main__':
    unittest.main()
