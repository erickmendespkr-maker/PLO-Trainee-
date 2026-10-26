"""Synthetic FFmpeg/FFprobe tests: timestamp observations, not poker recognition."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from offline_clip_decoded_pts_comparison import (build_report, decoded_pts,
                                                 export_report, _spacing)
from offline_manual_clip_export import export_clip


class DecodedPtsComparisonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.source = cls.root / 'cfr.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                        'testsrc2=size=160x120:rate=10:duration=5',
                        '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-y',
                        str(cls.source)], check=True)
        cls.source_sha = hashlib.sha256(cls.source.read_bytes()).hexdigest()
        cls.selection = {
            'schema_version': 1, 'recording_sha256': cls.source_sha,
            'table_id': 1, 'start_seconds': 0.55, 'end_seconds': 2.55,
            'human_selected': True, 'explanation': 'Apenas teste sintético',
            'reviewer_confidence': 0.6, 'crop': None,
        }
        selection_path = cls.root / 'selection.json'
        selection_path.write_text(json.dumps(cls.selection), encoding='utf-8')
        cls.clip = cls.root / 'clip.mp4'
        cls.sidecar = export_clip(cls.source, selection_path, cls.clip)
        cls.sidecar_path = cls.root / 'clip.json'
        cls.clip_sha = hashlib.sha256(cls.clip.read_bytes()).hexdigest()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def _build(self, sidecar=None, source=None, clip=None, **kwargs):
        return build_report(source or self.source, clip or self.clip,
                            sidecar or self.sidecar,
                            source_sha=self.source_sha, clip_sha=self.clip_sha,
                            **kwargs)

    def test_actual_cfr_pts_are_measured(self):
        report = self._build()
        self.assertTrue(report['actual_decoded_frame_pts_measured'])
        self.assertFalse(report['frame_exact_export_verified'])
        self.assertFalse(report['hand_reconstruction_verified'])
        self.assertFalse(report['strategic_error_established'])
        self.assertFalse(report['automatic_clip_selection_authorized'])
        self.assertEqual(report['table_id_human_selected'], 1)
        self.assertFalse(report['nonzero_clip_video_stream_start_pts_observed'])
        self.assertAlmostEqual(report['clip_video_stream_start_pts_seconds'], 0.0, places=3)
        self.assertGreaterEqual(report['clip_video_duration_shortfall_seconds'], 0)
        self.assertLessEqual(report['clip_video_duration_shortfall_seconds'], .25)
        self.assertEqual(len(report['samples']), 11)
        self.assertLess(report['max_sampled_abs_proximity_seconds'], .11)
        self.assertFalse(report['clip_pts_observation']['variable_spacing_observed_in_sample'])

    def test_cli_report_integrity_and_no_overwrite(self):
        path = self.root / 'pts_report.json'
        report = export_report(self.source, self.clip, self.sidecar_path, path)
        stored = json.loads(path.read_text(encoding='utf-8'))
        self.assertEqual(report, stored)
        self.assertEqual(stored['source_sha256'], self.source_sha)
        self.assertEqual(stored['clip_sha256'], self.clip_sha)
        self.assertEqual(stored['sidecar_sha256'],
                         hashlib.sha256(self.sidecar_path.read_bytes()).hexdigest())
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            export_report(self.source, self.clip, self.sidecar_path, path)

    def test_cfr_frame_spacing(self):
        pts = decoded_pts(self.source, 0, 4.0)
        self.assertGreater(len(pts), 30)
        self.assertAlmostEqual(_spacing(pts)['median_positive_gap_seconds'], .1, places=3)
        self.assertFalse(_spacing(pts)['variable_spacing_observed_in_sample'])

    def test_vfr_pts_and_manual_export(self):
        source = self.root / 'vfr.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                        'testsrc2=size=160x120:rate=10:duration=5',
                        '-vf', "select='not(mod(n,2))+not(mod(n,5))'",
                        '-fps_mode', 'vfr', '-c:v', 'libx264',
                        '-pix_fmt', 'yuv420p', '-y', str(source)], check=True)
        selection = copy.deepcopy(self.selection)
        selection['recording_sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
        p = self.root / 'vfr_selection.json'
        p.write_text(json.dumps(selection))
        clip = self.root / 'vfr_clip.mp4'
        export_clip(source, p, clip)
        report = export_report(source, clip, self.root / 'vfr_clip.json',
                               self.root / 'vfr_pts_report.json')
        self.assertTrue(report['source_pts_observation']['variable_spacing_observed_in_sample'])
        self.assertTrue(report['actual_decoded_frame_pts_measured'])
        self.assertFalse(report['frame_exact_export_verified'])
        self.assertLessEqual(len(report['samples']), 11)

    def test_four_manual_table_ids(self):
        for table in range(1, 5):
            with self.subTest(table=table):
                sidecar = copy.deepcopy(self.sidecar)
                sidecar['selection']['table_id'] = table
                report = self._build(sidecar)
                self.assertEqual(report['table_id_human_selected'], table)
                self.assertFalse(report['hand_start_or_end_pts_verified'])

    def test_invalid_tolerance(self):
        for value in (-1, 0, 0.51, float('nan'), True, '0.1'):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'tolerance'):
                self._build(tolerance_seconds=value)

    def test_wrong_sidecar_hash(self):
        bad = copy.deepcopy(self.sidecar)
        bad['output_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'SHA-256'):
            self._build(bad)

    def test_rejects_claimed_strategic_verdict(self):
        bad = copy.deepcopy(self.sidecar)
        bad['strategic_error_established'] = True
        with self.assertRaisesRegex(ValueError, 'verification'):
            self._build(bad)

    def test_rejects_false_automatic_selection(self):
        bad = copy.deepcopy(self.sidecar)
        bad['automatic_clip_selection_authorized'] = True
        with self.assertRaisesRegex(ValueError, 'verification'):
            self._build(bad)

    def test_rejects_duration_disagreement(self):
        bad = copy.deepcopy(self.sidecar)
        bad['output_duration_seconds'] += 2
        with self.assertRaisesRegex(ValueError, 'duration'):
            self._build(bad)

    def test_rejects_geometry_mismatch(self):
        bad = copy.deepcopy(self.sidecar)
        bad['selection']['crop'] = {'x': 0, 'y': 0, 'width': 80, 'height': 80}
        with self.assertRaisesRegex(ValueError, 'geometry'):
            self._build(bad)

    def test_rejects_tampered_mp4(self):
        bad_clip = self.root / 'tampered.mp4'
        bad_clip.write_bytes(self.clip.read_bytes() + b'extra')
        target = self.root / 'tampered_pts.json'
        with self.assertRaisesRegex(ValueError, 'SHA-256'):
            export_report(self.source, bad_clip, self.sidecar_path, target)
        self.assertFalse(target.exists())

    def test_rejects_symlink_media(self):
        linked = self.root / 'linked_source.mp4'
        linked.symlink_to(self.source)
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            export_report(linked, self.clip, self.sidecar_path,
                          self.root / 'symlink_pts.json')

    def test_rejects_symlink_sidecar(self):
        linked = self.root / 'linked_sidecar.json'
        linked.symlink_to(self.sidecar_path)
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            export_report(self.source, self.clip, linked,
                          self.root / 'symlink_sidecar_pts.json')

    def test_rejects_overlapping_output(self):
        with self.assertRaisesRegex(ValueError, 'overlap'):
            export_report(self.source, self.clip, self.sidecar_path, self.clip)

    def test_rejects_duplicate_json_key(self):
        bad = self.root / 'duplicate_pts_sidecar.json'
        bad.write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            export_report(self.source, self.clip, bad,
                          self.root / 'duplicate_pts_out.json')

    def test_rejects_nonzero_origin(self):
        offset = self.root / 'offset.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                        'testsrc2=size=160x120:rate=10:duration=5',
                        '-vf', 'setpts=PTS+5/TB', '-fps_mode', 'passthrough',
                        '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-y',
                        str(offset)], check=True)
        bad = copy.deepcopy(self.sidecar)
        bad['source_sha256'] = hashlib.sha256(offset.read_bytes()).hexdigest()
        bad['selection']['recording_sha256'] = bad['source_sha256']
        with self.assertRaisesRegex(ValueError, 'PTS origin'):
            build_report(offset, self.clip, bad, source_sha=bad['source_sha256'],
                         clip_sha=self.clip_sha)

    def test_rejects_missing_pts(self):
        with patch('offline_clip_decoded_pts_comparison.subprocess.run') as run:
            run.return_value.stdout = b''
            with self.assertRaisesRegex(ValueError, 'Empty'):
                decoded_pts(self.source, 0, 1)

    def test_rejects_nonfinite_pts(self):
        with patch('offline_clip_decoded_pts_comparison.subprocess.run') as run:
            run.return_value.stdout = b'NaN\n'
            with self.assertRaisesRegex(ValueError, 'Out-of-range'):
                decoded_pts(self.source, 0, 1)

    def test_rejects_oversized_probe_output(self):
        with patch('offline_clip_decoded_pts_comparison.subprocess.run') as run:
            run.return_value.stdout = b'0.1\n' * 600000
            with self.assertRaisesRegex(ValueError, 'oversized'):
                decoded_pts(self.source, 0, 1)

    def test_rejects_invalid_probe_window(self):
        for begin, span in [(-1, 1), (0, 0), (0, 211), (0, float('inf'))]:
            with self.subTest(begin=begin, span=span), self.assertRaises(ValueError):
                decoded_pts(self.source, begin, span)

    def test_rejects_changed_source_during_sampling(self):
        modified = self.root / 'changing_source.mp4'
        modified.write_bytes(self.source.read_bytes())
        with patch('offline_clip_decoded_pts_comparison.decoded_pts',
                   wraps=decoded_pts) as pts:
            def mutate(path, begin, span):
                if not mutate.done:
                    mutate.done = True
                    modified.write_bytes(modified.read_bytes() + b'changed')
                return decoded_pts(path, begin, span)
            mutate.done = False
            pts.side_effect = mutate
            with self.assertRaisesRegex(ValueError, 'changed'):
                export_report(modified, self.clip, self.sidecar_path,
                              self.root / 'changed_pts.json')
        self.assertFalse((self.root / 'changed_pts.json').exists())


if __name__ == '__main__':
    unittest.main()
