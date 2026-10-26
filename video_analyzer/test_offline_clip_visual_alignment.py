"""Synthetic-only visual comparison tests; no poker footage or strategic verdict."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from offline_clip_visual_alignment import build_report, export_report, _difference
from offline_manual_clip_export import export_clip


class VisualAlignmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.base = Path(cls.tmp.name)
        cls.source = cls.base / 'source.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                        'testsrc2=size=160x120:rate=10:duration=5',
                        '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-y', str(cls.source)],
                       check=True)
        cls.sel = {'schema_version': 1, 'recording_sha256': hashlib.sha256(cls.source.read_bytes()).hexdigest(),
                   'table_id': 2, 'start_seconds': .5, 'end_seconds': 2.5,
                   'human_selected': True, 'explanation': 'Apenas vídeo sintético',
                   'reviewer_confidence': .6,
                   'crop': {'x': 0, 'y': 0, 'width': 96, 'height': 96}}
        path = cls.base / 'sel.json'
        path.write_text(json.dumps(cls.sel))
        cls.clip = cls.base / 'clip.mp4'
        cls.sidecar = export_clip(cls.source, path, cls.clip)
        cls.sidecar_path = cls.base / 'clip.json'

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_real_ffmpeg_spot_check(self):
        report = export_report(self.source, self.clip, self.sidecar_path, self.base/'visual.json')
        self.assertEqual(len(report['samples']), 3)
        self.assertLess(report['mean_best_normalized_gray_mae'], .15)
        self.assertFalse(report['frame_exact_export_verified'])
        self.assertFalse(report['actual_decoded_frame_pts_measured'])
        self.assertFalse(report['hand_reconstruction_verified'])
        self.assertFalse(report['automatic_clip_selection_authorized'])
        self.assertEqual(report['table_id_human_selected'], 2)
        with self.assertRaises(ValueError):
            export_report(self.source, self.clip, self.sidecar_path, self.base/'visual.json')

    def test_four_tables_manual_identity(self):
        for table in (1, 2, 3, 4):
            with self.subTest(table=table):
                sidecar = copy.deepcopy(self.sidecar)
                sidecar['selection']['table_id'] = table
                r = build_report(self.source, self.clip, sidecar,
                                 source_sha=self.sel['recording_sha256'],
                                 clip_sha=hashlib.sha256(self.clip.read_bytes()).hexdigest())
                self.assertEqual(r['table_id_human_selected'], table)

    def test_rejects_forged_source_digest(self):
        fake = copy.deepcopy(self.sidecar)
        fake['source_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'SHA-256'):
            build_report(self.source, self.clip, fake,
                         source_sha=self.sel['recording_sha256'],
                         clip_sha=hashlib.sha256(self.clip.read_bytes()).hexdigest())

    def test_rejects_forged_authorization(self):
        fake = copy.deepcopy(self.sidecar)
        fake['hand_reconstruction_verified'] = True
        with self.assertRaisesRegex(ValueError, 'verification'):
            build_report(self.source, self.clip, fake,
                         source_sha=self.sel['recording_sha256'],
                         clip_sha=hashlib.sha256(self.clip.read_bytes()).hexdigest())

    def test_rejects_duplicate_json_key(self):
        bad = self.base / 'duplicate.json'
        bad.write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            export_report(self.source, self.clip, bad, self.base/'duplicate_output.json')

    def test_rejects_symlink(self):
        link = self.base/'link.mp4'
        link.symlink_to(self.source)
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            export_report(link, self.clip, self.sidecar_path, self.base/'symlink_output.json')

    def test_rejects_tampered_clip(self):
        tampered = self.base/'tampered.mp4'
        tampered.write_bytes(self.clip.read_bytes()+b'extra')
        with self.assertRaisesRegex(ValueError, 'SHA-256'):
            export_report(self.source, tampered, self.sidecar_path, self.base/'tampered.json')

    def test_no_output_on_ffmpeg_failure(self):
        target = self.base/'failure.json'
        with patch('offline_clip_visual_alignment._frame', side_effect=ValueError('synthetic failure')):
            with self.assertRaisesRegex(ValueError, 'synthetic failure'):
                export_report(self.source, self.clip, self.sidecar_path, target)
        self.assertFalse(target.exists())

    def test_difference_extremes(self):
        self.assertEqual(_difference(bytes([0])*1024, bytes([0])*1024), 0)
        self.assertEqual(_difference(bytes([0])*1024, bytes([255])*1024), 1)
        with self.assertRaises(ValueError):
            _difference(b'a', b'b')


    def test_vfr_source_remains_observational(self):
        vfr = self.base/'vfr_source.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                        'testsrc2=size=160x120:rate=10:duration=4',
                        '-vf', "select='not(mod(n,2))+not(mod(n,5))'",
                        '-fps_mode', 'vfr', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
                        '-y', str(vfr)], check=True)
        selection = copy.deepcopy(self.sel)
        selection['recording_sha256'] = hashlib.sha256(vfr.read_bytes()).hexdigest()
        selection['crop'] = None
        p = self.base/'vfr_selection.json'
        p.write_text(json.dumps(selection))
        clip = self.base/'vfr_clip.mp4'
        export_clip(vfr, p, clip)
        report = export_report(vfr, clip, self.base/'vfr_clip.json',
                               self.base/'vfr_alignment.json')
        self.assertEqual(len(report['samples']), 3)
        self.assertFalse(report['frame_exact_export_verified'])
        self.assertIn('VFR', ' '.join(report['limitations']))

    def test_nonzero_pts_source_rejected(self):
        offset = self.base/'offset.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                        'testsrc2=size=160x120:rate=10:duration=4',
                        '-vf', 'setpts=PTS+5/TB', '-fps_mode', 'passthrough',
                        '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-y', str(offset)],
                       check=True)
        selection = copy.deepcopy(self.sel)
        selection['recording_sha256'] = hashlib.sha256(offset.read_bytes()).hexdigest()
        selection['crop'] = None
        p = self.base/'offset_selection.json'
        p.write_text(json.dumps(selection))
        clip = self.base/'offset_clip.mp4'
        export_clip(offset, p, clip)
        with self.assertRaisesRegex(ValueError, 'PTS origin'):
            export_report(offset, clip, self.base/'offset_clip.json',
                          self.base/'offset_alignment.json')

    def test_source_changed_during_sampling(self):
        copy = self.base/'mutating_source.mp4'
        copy.write_bytes(self.source.read_bytes())
        with patch('offline_clip_visual_alignment._frame') as mocked:
            def changed(path, second, crop=None):
                if not changed.done:
                    changed.done = True
                    copy.write_bytes(copy.read_bytes() + b'tampered')
                return bytes([20]) * 1024
            changed.done = False
            mocked.side_effect = changed
            with self.assertRaisesRegex(ValueError, 'changed'):
                export_report(copy, self.clip, self.sidecar_path,
                              self.base/'mutating_report.json')
        self.assertFalse((self.base/'mutating_report.json').exists())

    def test_geometry_mismatch(self):
        forged = copy.deepcopy(self.sidecar)
        forged['selection']['crop'] = {'x': 0, 'y': 0, 'width': 80, 'height': 80}
        with self.assertRaisesRegex(ValueError, 'geometry'):
            build_report(self.source, self.clip, forged,
                         source_sha=self.sel['recording_sha256'],
                         clip_sha=hashlib.sha256(self.clip.read_bytes()).hexdigest())

    def test_sidecar_symlink_rejected(self):
        link = self.base/'sidecar_link.json'
        link.symlink_to(self.sidecar_path)
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            export_report(self.source, self.clip, link, self.base/'sidecar_link_output.json')

if __name__ == '__main__':
    unittest.main()
