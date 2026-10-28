"""Synthetic-only FFmpeg integration and adversarial validation for dense refinement."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from offline_video_ingest_probe import build
from offline_sampled_visual_change import analyze
from offline_adaptive_change_refinement import refine, schedule, read_changes


class DenseRefinementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.video = cls.root / 'synthetic.mp4'
        vf = ("drawbox=x=0:y=0:w=320:h=180:color=white:t=fill:enable='gte(t,2)',"
              "drawbox=x=320:y=180:w=320:h=180:color=white:t=fill:enable='gte(t,5)'")
        subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi',
                        '-i', 'color=c=gray:s=640x360:r=1', '-t', '8',
                        '-vf', vf, '-c:v', 'mpeg4', '-y', str(cls.video)],
                       check=True, capture_output=True)
        cls.regions = cls.root / 'regions.json'
        cls.regions.write_text(json.dumps({'tables': [
            {'table_id': i + 1, 'x': (i % 2) * 320,
             'y': (i // 2) * 180, 'width': 320, 'height': 180}
            for i in range(4)]}))
        cls.ingest = cls.root / 'ingest'
        build(cls.video, cls.regions, cls.ingest)
        cls.changes_dir = cls.root / 'changes'
        analyze(cls.ingest, cls.changes_dir)
        cls.changes = cls.changes_dir / 'visual_changes.json'

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def run_refine(self, **kwargs):
        return refine(self.video, self.regions, self.ingest, self.changes,
                      self.path / 'refined', **kwargs)

    def test_four_table_integration_and_tightened_brackets(self):
        result = self.run_refine()
        self.assertEqual([x['table_id'] for x in result['refinements']], [1, 4])
        self.assertEqual([len(x['new_frames']) for x in result['refinements']], [3, 2])
        self.assertEqual(result['refinements'][0]['visual_transition_brackets'][0]['to_seconds'], 2.0)
        self.assertEqual(result['refinements'][1]['visual_transition_brackets'][0]['to_seconds'], 5.0)
        self.assertTrue(all(x['hand_boundary_confidence'] is None for x in result['refinements']))
        self.assertFalse(result['hands_reconstructed'])
        self.assertEqual(json.loads((self.path / 'refined' / 'dense_refinement.json').read_text()), result)

    def test_output_must_be_new(self):
        (self.path / 'refined').mkdir()
        with self.assertRaises(ValueError):
            self.run_refine()

    def test_invalid_step_rejected(self):
        for step in (0, True, float('nan'), float('inf'), 0.1, 6):
            with self.subTest(step=step), self.assertRaises(ValueError):
                self.run_refine(step=step)
        self.assertFalse((self.path / 'refined').exists())

    def test_source_video_tamper_rejected(self):
        fake = self.path / 'fake.mp4'
        shutil.copyfile(self.video, fake)
        fake.write_bytes(fake.read_bytes() + b'tamper')
        with self.assertRaisesRegex(ValueError, 'Source video'):
            refine(fake, self.regions, self.ingest, self.changes, self.path / 'refined')

    def test_region_tamper_rejected(self):
        fake = self.path / 'regions.json'
        fake.write_text(self.regions.read_text() + ' ')
        with self.assertRaisesRegex(ValueError, 'Source video or region'):
            refine(self.video, fake, self.ingest, self.changes, self.path / 'refined')

    def test_manifest_hash_mismatch_rejected(self):
        copied = self.path / 'ingest'
        shutil.copytree(self.ingest, copied)
        (copied / 'manifest.json').write_text((copied / 'manifest.json').read_text() + ' ')
        with self.assertRaisesRegex(ValueError, 'does not match'):
            refine(self.video, self.regions, copied, self.changes, self.path / 'refined')

    def test_bad_endpoint_rejected(self):
        self._mutate(lambda d: d['candidate_intervals'][0].update(previous_file='../escape.jpg'))
        with self.assertRaisesRegex(ValueError, 'endpoints'):
            self.run_refine_with_modified()

    def test_bad_timestamp_rejected(self):
        self._mutate(lambda d: d['candidate_intervals'][0].update(latest_possible_change_seconds=7))
        with self.assertRaisesRegex(ValueError, 'timestamps'):
            self.run_refine_with_modified()

    def test_oversized_interval_rejected(self):
        with self.assertRaisesRegex(ValueError, 'limit'):
            schedule(0, 61, 0.5, 1)

    def test_budget_exceeded_rejected(self):
        self._mutate(lambda d: d.update(candidate_intervals=d['candidate_intervals'] * 64))
        with self.assertRaisesRegex(ValueError, 'schema'):
            self.run_refine_with_modified()

    def test_detector_threshold_rejected(self):
        self._mutate(lambda d: d['detector'].update(threshold=float('nan')))
        with self.assertRaises(ValueError):
            self.run_refine_with_modified()

    def test_duplicate_json_key_rejected(self):
        bad = self.path / 'changes.json'
        bad.write_text(self.changes.read_text().replace('"schema_version": 1,',
                                                      '"schema_version": 1, "schema_version": 1,'))
        with self.assertRaisesRegex(ValueError, 'Duplicate JSON key'):
            read_changes(bad)

    def test_no_candidates_yields_empty_report(self):
        self._mutate(lambda d: d.update(candidate_intervals=[]))
        result = self.run_refine_with_modified()
        self.assertEqual(result['refinements'], [])

    def test_sample_hash_tamper_rejected(self):
        copied = self.path / 'ingest'
        shutil.copytree(self.ingest, copied)
        next(copied.glob('*.jpg')).write_bytes(b'not the original')
        with self.assertRaisesRegex(ValueError, 'modified'):
            refine(self.video, self.regions, copied, self.changes, self.path / 'refined')

    def test_schedule_nominal_fps(self):
        self.assertEqual(schedule(0, 4, 0.5, 1), [1, 2, 3])
        self.assertEqual(schedule(0, 1, 0.25, 2), [0.5])

    def _mutate(self, fn):
        data = json.loads(self.changes.read_text())
        fn(data)
        (self.path / 'changes.json').write_text(json.dumps(data))

    def run_refine_with_modified(self):
        return refine(self.video, self.regions, self.ingest,
                      self.path / 'changes.json', self.path / 'refined')


if __name__ == '__main__':
    unittest.main()
