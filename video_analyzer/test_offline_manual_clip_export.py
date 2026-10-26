"""Synthetic, offline-only FFmpeg clip export tests."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from offline_manual_clip_export import export_clip, read_selection, validate_selection, probe


class ClipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.base = Path(cls.tmp.name)
        cls.video = cls.base / 'source.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                        'testsrc2=size=320x240:rate=10:duration=4', '-c:v', 'libx264',
                        '-pix_fmt', 'yuv420p', '-y', str(cls.video)], check=True)
        cls.selection = {'schema_version': 1,
                         'recording_sha256': hashlib.sha256(cls.video.read_bytes()).hexdigest(),
                         'table_id': 2, 'start_seconds': .5, 'end_seconds': 2.5,
                         'human_selected': True, 'explanation': 'Mão sintética para revisão.',
                         'reviewer_confidence': .6,
                         'crop': {'x': 0, 'y': 0, 'width': 160, 'height': 120}}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_real_ffmpeg_clip_and_subtitle(self):
        p = self.base / 'manual.json'
        p.write_text(json.dumps(self.selection))
        out = self.base / 'manual_clip.mp4'
        report = export_clip(self.video, p, out)
        self.assertEqual(report['status'], 'manual_clip_not_video_hand_verified')
        self.assertFalse(report['source_pts_boundaries_verified'])
        self.assertFalse(report['math_analysis_linked'])
        self.assertEqual(probe(out)['width'], 160)
        self.assertEqual(probe(out)['height'], 120)
        self.assertTrue((self.base / 'manual_clip.json').exists())
        streams = json.loads(subprocess.check_output(['ffprobe', '-v', 'error',
            '-show_entries', 'stream=codec_type', '-of', 'json', str(out)]))['streams']
        self.assertIn('subtitle', [s['codec_type'] for s in streams])
        self.assertEqual(hashlib.sha256(out.read_bytes()).hexdigest(), report['output_sha256'])
        with self.assertRaises(ValueError):
            export_clip(self.video, p, out)

    def test_rejects_bad_selection_fields(self):
        for field, value in [('human_selected', False), ('table_id', 5),
                             ('start_seconds', True), ('end_seconds', 9999),
                             ('reviewer_confidence', 1.1), ('explanation', ''),
                             ('crop', {'x': 300, 'y': 0, 'width': 160, 'height': 120})]:
            with self.subTest(field=field):
                sel = copy.deepcopy(self.selection)
                sel[field] = value
                p = self.base / f'invalid_{field}.json'
                p.write_text(json.dumps(sel))
                with self.assertRaises(ValueError):
                    export_clip(self.video, p, self.base / f'invalid_{field}.mp4')

    def test_source_tamper_blocks(self):
        sel = copy.deepcopy(self.selection)
        sel['recording_sha256'] = '0' * 64
        p = self.base / 'tampered.json'
        p.write_text(json.dumps(sel))
        with self.assertRaisesRegex(ValueError, 'SHA-256'):
            export_clip(self.video, p, self.base / 'tampered_output.mp4')

    def test_duplicate_json_key_and_symlink(self):
        p = self.base / 'duplicate.json'
        p.write_text('{"table_id":1,"table_id":2}')
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            read_selection(p)
        link = self.base / 'linked.json'
        link.symlink_to(p)
        with self.assertRaises(ValueError):
            read_selection(link)

    def test_selection_outside_duration_and_no_crop(self):
        sel = copy.deepcopy(self.selection)
        sel['crop'] = None
        sel['start_seconds'] = 3.0
        sel['end_seconds'] = 4.5
        p = self.base / 'overrun.json'
        p.write_text(json.dumps(sel))
        with self.assertRaisesRegex(ValueError, 'timeline'):
            export_clip(self.video, p, self.base / 'overrun_output.mp4')
        self.assertTrue(validate_selection(sel))

    def test_no_live_or_math_authorization_in_report(self):
        p = self.base / 'plain.json'
        sel = copy.deepcopy(self.selection)
        sel['crop'] = None
        p.write_text(json.dumps(sel))
        out = self.base / 'plain_output.mp4'
        report = export_clip(self.video, p, out)
        self.assertFalse(report['strategic_error_established'])
        self.assertFalse(report['automatic_clip_selection_authorized'])
        self.assertFalse(report['hand_reconstruction_verified'])
        self.assertEqual(probe(out)['width'], 320)


if __name__ == '__main__':
    unittest.main()