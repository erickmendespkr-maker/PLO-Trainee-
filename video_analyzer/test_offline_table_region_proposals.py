"""FFmpeg-generated, offline-only layout-proposal regression tests."""
from __future__ import annotations
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import offline_table_region_proposals as mod


def synthetic(path, mode='four'):
    filters = {
        'four': ('drawbox=x=0:y=0:w=320:h=180:color=red:t=fill,'
                 'drawbox=x=320:y=0:w=320:h=180:color=green:t=fill,'
                 'drawbox=x=0:y=180:w=320:h=180:color=blue:t=fill,'
                 'drawbox=x=320:y=180:w=320:h=180:color=yellow:t=fill'),
        'vertical': ('drawbox=x=0:y=0:w=320:h=360:color=red:t=fill,'
                     'drawbox=x=320:y=0:w=320:h=360:color=blue:t=fill'),
        'horizontal': ('drawbox=x=0:y=0:w=640:h=180:color=red:t=fill,'
                       'drawbox=x=0:y=180:w=640:h=180:color=blue:t=fill'),
        'flat': 'null',
    }
    subprocess.run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y',
                    '-f','lavfi','-i','color=c=gray:s=640x360:r=10:d=2',
                    '-vf',filters[mode],'-c:v','libx264','-pix_fmt','yuv420p',str(path)],
                   check=True, capture_output=True, timeout=40)


class ProposalsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = tempfile.TemporaryDirectory(prefix='plo_regions_fixture_')
        cls.base = Path(cls.fixture.name)
        for mode in ('four','vertical','horizontal','flat'):
            synthetic(cls.base / f'{mode}.mp4', mode)

    @classmethod
    def tearDownClass(cls):
        cls.fixture.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='plo_regions_test_')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.out = self.root / 'output'
        self.out.mkdir()

    def produce(self, mode='four'):
        return mod.propose(self.base / f'{mode}.mp4', self.out)

    def test_four_quadrants(self):
        data = self.produce()
        self.assertEqual(len(data['regions']), 4)
        self.assertEqual([r['table_id'] for r in data['regions']], ['T1','T2','T3','T4'])
        self.assertTrue(data['vertical_seam_evidence']['supported_by_heuristic'])
        self.assertTrue(data['horizontal_seam_evidence']['supported_by_heuristic'])
        self.assertFalse(data['automatic_ocr_math_authorization'])
        self.assertFalse(data['human_confirmation'])
        self.assertEqual(data['source_video_sha256'], mod.sha256(self.base / 'four.mp4'))
        self.assertEqual(data['preview_sha256'], mod.sha256(self.out / 'preview.png'))
        self.assertTrue(all(r['width'] % 2 == r['height'] % 2 == 0 for r in data['regions']))

    def test_vertical_only(self):
        data = self.produce('vertical')
        self.assertEqual(len(data['regions']), 2)
        self.assertEqual(data['regions'][0]['y'], 0)

    def test_horizontal_only(self):
        data = self.produce('horizontal')
        self.assertEqual(len(data['regions']), 2)
        self.assertEqual(data['regions'][0]['x'], 0)

    def test_flat_single_region(self):
        data = self.produce('flat')
        self.assertEqual(len(data['regions']), 1)
        self.assertFalse(data['vertical_seam_evidence']['supported_by_heuristic'])
        self.assertFalse(data['horizontal_seam_evidence']['supported_by_heuristic'])

    def test_reproducible_proposals(self):
        a = self.produce()
        other = self.root / 'other'
        other.mkdir()
        b = mod.propose(self.base / 'four.mp4', other)
        self.assertEqual(a, b)
        self.assertEqual((self.out / 'proposals.json').read_bytes(),
                         (other / 'proposals.json').read_bytes())

    def test_collision_does_not_overwrite(self):
        (self.out / 'preview.png').write_bytes(b'existing')
        with self.assertRaises(ValueError):
            self.produce()
        self.assertEqual((self.out / 'preview.png').read_bytes(), b'existing')
        self.assertFalse((self.out / 'proposals.json').exists())

    def test_no_symlink_output_dir(self):
        link = self.root / 'alias'
        link.symlink_to(self.out, target_is_directory=True)
        with self.assertRaises(ValueError):
            mod.propose(self.base / 'four.mp4', link)

    def test_explicit_confirmation_required(self):
        self.produce()
        target = self.out / 'manual.json'
        with self.assertRaises(ValueError):
            mod.confirm(self.base / 'four.mp4', self.out / 'proposals.json', target)
        self.assertFalse(target.exists())

    def test_confirm_existing_crop_schema(self):
        self.produce()
        target = self.out / 'manual.json'
        layout = mod.confirm(self.base / 'four.mp4', self.out / 'proposals.json', target,
                             confirmed=True)
        self.assertEqual(set(layout), {'schema_version','status','source_video_sha256','regions'})
        self.assertEqual(layout['status'], mod.MANUAL_STATUS)
        self.assertEqual(json.loads(target.read_text()), layout)

    def test_confirm_wrong_video(self):
        self.produce()
        with self.assertRaises(ValueError):
            mod.confirm(self.base / 'flat.mp4', self.out / 'proposals.json',
                        self.out / 'manual.json', confirmed=True)

    def test_confirm_tampered_preview(self):
        self.produce()
        with (self.out / 'preview.png').open('ab') as f:
            f.write(b'tamper')
        with self.assertRaises(ValueError):
            mod.confirm(self.base / 'four.mp4', self.out / 'proposals.json',
                        self.out / 'manual.json', confirmed=True)

    def test_confirm_invalid_geometry(self):
        self.produce()
        p = self.out / 'proposals.json'
        data = json.loads(p.read_text())
        data['regions'][0]['width'] = 641
        p.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            mod.confirm(self.base / 'four.mp4', p, self.out / 'manual.json', confirmed=True)

    def test_confirm_valid_but_modified_geometry_rejected(self):
        self.produce()
        p = self.out / 'proposals.json'
        data = json.loads(p.read_text())
        data['regions'][0]['width'] -= 2
        p.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            mod.confirm(self.base / 'four.mp4', p, self.out / 'manual.json', confirmed=True)

    def test_confirm_duplicate_table(self):
        self.produce()
        p = self.out / 'proposals.json'
        data = json.loads(p.read_text())
        data['regions'][1]['table_id'] = 'T1'
        p.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            mod.confirm(self.base / 'four.mp4', p, self.out / 'manual.json', confirmed=True)

    def test_confirm_rejects_ocr_authorization(self):
        self.produce()
        p = self.out / 'proposals.json'
        data = json.loads(p.read_text())
        data['automatic_ocr_math_authorization'] = True
        p.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            mod.confirm(self.base / 'four.mp4', p, self.out / 'manual.json', confirmed=True)

    def test_confirm_rejects_duplicate_json_keys(self):
        self.produce()
        p = self.out / 'proposals.json'
        p.write_text(p.read_text().replace('"schema_version": 1',
                                            '"schema_version": 1, "schema_version": 1', 1))
        with self.assertRaises(ValueError):
            mod.confirm(self.base / 'four.mp4', p, self.out / 'manual.json', confirmed=True)

    def test_confirm_output_collision(self):
        self.produce()
        target = self.out / 'manual.json'
        target.write_text('keep me')
        with self.assertRaises(ValueError):
            mod.confirm(self.base / 'four.mp4', self.out / 'proposals.json', target,
                        confirmed=True)
        self.assertEqual(target.read_text(), 'keep me')

    def test_confirm_symlink_preview(self):
        self.produce()
        p = self.out / 'preview.png'
        p.rename(self.out / 'original.png')
        p.symlink_to(self.out / 'original.png')
        with self.assertRaises(ValueError):
            mod.confirm(self.base / 'four.mp4', self.out / 'proposals.json',
                        self.out / 'manual.json', confirmed=True)

    def test_confirm_nan_rejected(self):
        self.produce()
        p = self.out / 'proposals.json'
        p.write_text(p.read_text().replace('"source_duration_seconds": 2.0',
                                            '"source_duration_seconds": NaN'))
        with self.assertRaises(ValueError):
            mod.confirm(self.base / 'four.mp4', p, self.out / 'manual.json', confirmed=True)


if __name__ == '__main__':
    unittest.main()
