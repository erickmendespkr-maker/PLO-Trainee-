"""FFmpeg/ffprobe integration tests on a generated synthetic local video."""
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import offline_reviewed_clip_export as clips


class ClipExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.video = cls.root / 'four_tables.mp4'
        subprocess.run(['ffmpeg', '-nostdin', '-loglevel', 'error', '-y',
                        '-f', 'lavfi', '-i', 'testsrc=size=640x360:rate=10:duration=3',
                        '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(cls.video)],
                       check=True, capture_output=True, timeout=30)
        cls.sha = clips.digest(cls.video)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.tmp_case = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp_case.cleanup)
        self.dir = Path(self.tmp_case.name)
        self.request = {'schema_version': 1, 'hand_id': 'synthetic-hand-1',
                        'table_id': 1, 'start_seconds': .5, 'end_seconds': 1.5,
                        'crop': {'x': 0, 'y': 0, 'width': 320, 'height': 180},
                        'explanation': 'Synthetic scene for offline clip validation',
                        'source_video_sha256': self.sha,
                        'reviewer_confirmed_offline': True}

    def run_export(self, request=None, *, video=None, output=None):
        p = self.dir / 'request.json'
        p.write_text(json.dumps(request if request is not None else self.request))
        return clips.export(video or self.video, p, output or self.dir / 'clip.mp4')

    def test_exports_valid_mp4_and_sidecar(self):
        report = self.run_export()
        clip = self.dir / 'clip.mp4'
        self.assertTrue(clip.is_file())
        self.assertEqual(clips.digest(clip), report['clip_sha256'])
        self.assertEqual(json.loads((self.dir / 'clip.mp4.json').read_text()), report)
        w, h, duration = clips.probe(clip)
        self.assertEqual((w, h), (320, 180))
        self.assertAlmostEqual(duration, 1.0, delta=.15)
        self.assertFalse(report['audio_included'])
        self.assertFalse(report['automatic_clip_selection_authorized'])

    def test_four_table_regions(self):
        regions = [(0, 0), (320, 0), (0, 180), (320, 180)]
        for i, (x, y) in enumerate(regions, 1):
            with self.subTest(table=i):
                r = copy.deepcopy(self.request)
                r['table_id'] = i
                r['crop']['x'] = x; r['crop']['y'] = y
                report = self.run_export(r, output=self.dir / f'clip{i}.mp4')
                self.assertEqual(report['table_id'], i)
                self.assertEqual(clips.probe(self.dir / f'clip{i}.mp4')[:2], (320, 180))

    def test_rejects_wrong_hash(self):
        r = copy.deepcopy(self.request); r['source_video_sha256'] = '0' * 64
        with self.assertRaises(ValueError): self.run_export(r)

    def test_rejects_missing_approval(self):
        r = copy.deepcopy(self.request); r['reviewer_confirmed_offline'] = False
        with self.assertRaises(ValueError): self.run_export(r)

    def test_rejects_missing_explanation(self):
        r = copy.deepcopy(self.request); r['explanation'] = ' '
        with self.assertRaises(ValueError): self.run_export(r)

    def test_rejects_unknown_field(self):
        r = copy.deepcopy(self.request); r['auto_upload'] = True
        with self.assertRaises(ValueError): self.run_export(r)

    def test_rejects_invalid_table(self):
        for i in (0, 5, True, '1'):
            with self.subTest(i=i):
                r = copy.deepcopy(self.request); r['table_id'] = i
                with self.assertRaises(ValueError): self.run_export(r)

    def test_rejects_crop_outside_frame(self):
        r = copy.deepcopy(self.request); r['crop']['x'] = 400
        with self.assertRaises(ValueError): self.run_export(r)

    def test_rejects_odd_crop(self):
        r = copy.deepcopy(self.request); r['crop']['width'] = 319
        with self.assertRaises(ValueError): self.run_export(r)

    def test_rejects_negative_crop(self):
        r = copy.deepcopy(self.request); r['crop']['y'] = -2
        with self.assertRaises(ValueError): self.run_export(r)

    def test_rejects_end_beyond_video(self):
        r = copy.deepcopy(self.request); r['end_seconds'] = 4
        with self.assertRaises(ValueError): self.run_export(r)

    def test_rejects_zero_length_clip(self):
        r = copy.deepcopy(self.request); r['end_seconds'] = r['start_seconds']
        with self.assertRaises(ValueError): self.run_export(r)

    def test_rejects_negative_time(self):
        r = copy.deepcopy(self.request); r['start_seconds'] = -1
        with self.assertRaises(ValueError): self.run_export(r)

    def test_rejects_existing_clip(self):
        (self.dir / 'clip.mp4').write_text('do not overwrite')
        with self.assertRaises(ValueError): self.run_export()
        self.assertEqual((self.dir / 'clip.mp4').read_text(), 'do not overwrite')

    def test_rejects_existing_sidecar(self):
        (self.dir / 'clip.mp4.json').write_text('do not overwrite')
        with self.assertRaises(ValueError): self.run_export()

    def test_rejects_symlink_video(self):
        link = self.dir / 'link.mp4'; link.symlink_to(self.video)
        with self.assertRaises(ValueError): self.run_export(video=link)

    def test_rejects_symlink_request(self):
        p = self.dir / 'source.json'; p.write_text(json.dumps(self.request))
        link = self.dir / 'request.json'; link.symlink_to(p)
        with self.assertRaises(ValueError): clips.export(self.video, link, self.dir / 'clip.mp4')

    def test_rejects_duplicate_json_key(self):
        p = self.dir / 'request.json'; p.write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaises(ValueError): clips.export(self.video, p, self.dir / 'clip.mp4')

    def test_rejects_invalid_json_nan(self):
        p = self.dir / 'request.json'; p.write_text('{"start_seconds":NaN}')
        with self.assertRaises(ValueError): clips.export(self.video, p, self.dir / 'clip.mp4')

    def test_rejects_output_not_mp4(self):
        with self.assertRaises(ValueError): self.run_export(output=self.dir / 'clip.webm')

    def test_rejects_nonvideo_file(self):
        p = self.dir / 'fake.mp4'; p.write_text('not a video')
        with self.assertRaises(ValueError): self.run_export(video=p)


if __name__ == '__main__':
    unittest.main()
