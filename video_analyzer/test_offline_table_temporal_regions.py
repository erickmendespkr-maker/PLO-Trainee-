"""Synthetic offline temporal-layout tests. No real poker video or live client."""
from __future__ import annotations
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import offline_table_temporal_regions as mod


def synthetic(path, mode='moving'):
    # Portable binary PPM frames; deterministic color boundaries move at t=3s.
    frames = path.parent / (path.stem + '_frames')
    frames.mkdir()
    for i in range(12):
        x = 160 + (24 if i >= 6 and mode == 'moving' else 0)
        y = 90 + (12 if i >= 6 and mode == 'moving' else 0)
        with (frames / f'frame_{i:03d}.ppm').open('wb') as f:
            f.write(b'P6\n320 180\n255\n')
            for row in range(180):
                if mode == 'flat':
                    line = bytes([90, 90, 90]) * 320
                else:
                    a, b = ((10, 250) if row < y else (220, 30))
                    line = bytes([a, a, a]) * x + bytes([b, b, b]) * (320 - x)
                f.write(line)
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-framerate', '2',
                    '-i', str(frames / 'frame_%03d.ppm'), '-c:v', 'libx264',
                    '-pix_fmt', 'yuv420p', str(path)], check=True, capture_output=True, timeout=40)


class TemporalRegionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = tempfile.TemporaryDirectory(prefix='plo_temporal_fixture_')
        cls.root = Path(cls.fixture.name)
        for mode in ('moving', 'static', 'flat'):
            synthetic(cls.root / f'{mode}.mp4', mode)

    @classmethod
    def tearDownClass(cls):
        cls.fixture.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='plo_temporal_test_')
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name)

    def run_track(self, mode='moving', **kw):
        return mod.track(self.root / f'{mode}.mp4', self.out, interval=1, **kw)

    def test_moving_boundaries_flagged_not_approved(self):
        data = self.run_track()
        self.assertEqual(len(data['observations']), 6)
        self.assertTrue(any(e['type'] == 'region_shift_candidate' for e in data['transitions']))
        self.assertTrue(all(e['requires_human_review'] for e in data['transitions']))
        self.assertFalse(data['crop_authorized'])
        self.assertFalse(data['automatic_ocr_math_authorization'])
        self.assertFalse(data['human_confirmation'])
        self.assertEqual(json.loads((self.out / 'temporal_regions.json').read_text()), data)
        self.assertTrue(all(len(x['regions']) == 4 for x in data['observations']))

    def test_static_has_no_shift(self):
        data = self.run_track('static')
        self.assertFalse(data['transitions'])
        self.assertEqual(len(data['observations']), 6)

    def test_flat_does_not_claim_table_detection(self):
        data = self.run_track('flat')
        self.assertTrue(all(x['status'] == 'unsupported' for x in data['observations']))
        self.assertFalse(data['human_confirmation'])

    def test_collision_preserves_existing(self):
        dest = self.out / 'temporal_regions.json'
        dest.write_text('keep')
        with self.assertRaisesRegex(ValueError, 'collision'):
            self.run_track()
        self.assertEqual(dest.read_text(), 'keep')

    def test_symlink_output_rejected(self):
        alias = self.out / 'alias'
        alias.symlink_to(self.out, target_is_directory=True)
        with self.assertRaises(ValueError):
            mod.track(self.root / 'moving.mp4', alias, interval=1)

    def test_sampling_budget_fail_closed(self):
        with self.assertRaisesRegex(ValueError, 'budget'):
            self.run_track(max_samples=2)
        self.assertFalse((self.out / 'temporal_regions.json').exists())

    def test_reject_boolean_interval(self):
        with self.assertRaises(ValueError):
            mod.track(self.root / 'moving.mp4', self.out, interval=True)

    def test_reject_invalid_frame(self):
        with self.assertRaises(ValueError):
            mod.analyze_frames([b'a', b'b'], [0.5, 1.5], 320, 180)

    def test_topology_change_is_ambiguous(self):
        old = [{'x':0,'y':0,'width':160,'height':180,'table_id':'T1'},
               {'x':160,'y':0,'width':160,'height':180,'table_id':'T2'}]
        new = [{'x':0,'y':0,'width':320,'height':180,'table_id':'T1'}]
        self.assertEqual(mod.compare(old,new,320,180)[0], 'topology_change_ambiguous')

    def test_large_shift_is_ambiguous(self):
        old = [{'x':0,'y':0,'width':160,'height':180,'table_id':'T1'},
               {'x':160,'y':0,'width':160,'height':180,'table_id':'T2'}]
        new = [{'x':0,'y':0,'width':240,'height':180,'table_id':'T1'},
               {'x':240,'y':0,'width':80,'height':180,'table_id':'T2'}]
        self.assertEqual(mod.compare(old,new,320,180)[0], 'large_shift_ambiguous')

    def test_no_exact_transition_claim(self):
        data = self.run_track()
        for event in data['transitions']:
            a, b = event['possible_change_window_seconds']
            self.assertLess(a, b)
            self.assertEqual(b, event['first_observed_at_seconds'])


if __name__ == '__main__':
    unittest.main()
