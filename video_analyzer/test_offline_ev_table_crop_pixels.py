"""Synthetic pixel-level verification that four table crops select distinct regions."""
import subprocess
import unittest

import test_offline_ev_table_crop as fixtures


class CropPixels(unittest.TestCase):
    def test_crop_quadrants_have_expected_center_colors(self):
        fixtures.CropTests.setUpClass()
        self.addCleanup(fixtures.CropTests.tearDownClass)
        fixture = fixtures.CropTests('test_four_table_render_and_hashes')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.make(4)
        fixture.run_export()
        expected = [(250, 0, 0), (0, 125, 0), (0, 0, 250), (250, 250, 0)]
        for i, rgb in enumerate(expected):
            path = fixture.out / f'crop_clip-{i}.mp4'
            frame = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(path),
                                    '-frames:v', '1', '-f', 'rawvideo',
                                    '-pix_fmt', 'rgb24', 'pipe:1'],
                                   capture_output=True, check=True, timeout=30).stdout
            self.assertEqual(len(frame), 320 * 180 * 3)
            pos = (90 * 320 + 160) * 3
            actual = frame[pos:pos+3]
            self.assertTrue(all(abs(a-b) <= 30 for a, b in zip(actual, rgb)),
                            f'crop {i}: expected {rgb}, got {tuple(actual)}')


if __name__ == '__main__':
    unittest.main()
