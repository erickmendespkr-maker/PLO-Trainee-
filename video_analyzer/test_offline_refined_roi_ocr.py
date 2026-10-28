"""Synthetic FFmpeg/Tesseract tests; no poker recordings or live services."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from offline_video_ingest_probe import build
from offline_sampled_visual_change import analyze
from offline_adaptive_change_refinement import refine
from offline_refined_roi_ocr import (evidence_index, load_json, parse_tsv, scan)


class RefinedRoiOcrTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.video = cls.root / 'synthetic.mp4'
        # Two of four table regions change. No real cards, actions or poker facts.
        vf = ("drawbox=x=0:y=0:w=320:h=180:color=white:t=fill:enable='gte(t,2)',"
              "drawbox=x=320:y=180:w=320:h=180:color=white:t=fill:enable='gte(t,5)',"
              "drawtext=text='POT 125':x=10:y=15:fontsize=34:fontcolor=black:enable='gte(t,2)'")
        subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi',
                        '-i', 'color=c=gray:s=640x360:r=1', '-t', '8',
                        '-vf', vf, '-c:v', 'mpeg4', '-y', str(cls.video)],
                       check=True, capture_output=True, timeout=60)
        cls.regions = cls.root / 'regions.json'
        cls.regions.write_text(json.dumps({'tables': [
            {'table_id': i + 1, 'x': (i % 2) * 320,
             'y': (i // 2) * 180, 'width': 320, 'height': 180}
            for i in range(4)]}), encoding='utf-8')
        cls.ingest = cls.root / 'ingest'
        build(cls.video, cls.regions, cls.ingest)
        cls.change_dir = cls.root / 'changes'
        analyze(cls.ingest, cls.change_dir)
        cls.changes = cls.change_dir / 'visual_changes.json'
        cls.refined = cls.root / 'refined'
        refine(cls.video, cls.regions, cls.ingest, cls.changes, cls.refined)
        cls.manifest, cls.ingest_sha, cls.changes_sha, cls.dense_sha, cls.frames = evidence_index(
            cls.ingest, cls.changes, cls.refined)
        cls.dense = json.loads((cls.refined / 'dense_refinement.json').read_text())
        assert len(cls.dense['refinements']) == 2

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.temp_case = tempfile.TemporaryDirectory()
        self.case = Path(self.temp_case.name)
        self.tasks = self.case / 'tasks.json'
        self.out = self.case / 'output'
        first = self.dense['refinements'][0]
        self.data = {'schema_version': 1,
                     'source_ingest_manifest_sha256': self.ingest_sha,
                     'source_dense_refinement_sha256': self.dense_sha,
                     'tasks': [
                         {'table_id': first['table_id'],
                          'frame_file': first['new_frames'][0]['file'],
                          'field': 'pot',
                          'roi': {'x': 0, 'y': 0, 'width': 100, 'height': 40}},
                         {'table_id': first['table_id'],
                          'frame_file': self.dense['refinements'][0]['new_frames'][-1]['file'],
                          'field': 'pot',
                          'roi': {'x': 0, 'y': 0, 'width': 220, 'height': 90}},
                         {'table_id': self.dense['refinements'][1]['table_id'],
                          'frame_file': self.dense['refinements'][1]['new_frames'][0]['file'],
                          'field': 'action',
                          'roi': {'x': 20, 'y': 20, 'width': 80, 'height': 40}}]}
        self.save()

    def tearDown(self):
        self.temp_case.cleanup()

    def save(self):
        self.tasks.write_text(json.dumps(self.data), encoding='utf-8')

    def scan(self, **overrides):
        args = {'recording': self.video, 'regions_json': self.regions,
                'ingest_dir': self.ingest, 'changes_json': self.changes,
                'refined_dir': self.refined, 'tasks_json': self.tasks,
                'output_dir': self.out}
        args.update(overrides)
        return scan(**args)

    def test_end_to_end_four_table_source_three_proposals(self):
        result = self.scan()
        self.assertEqual(len(result['proposals']), 3)
        self.assertEqual([x['table_id'] for x in result['proposals']], [1, 1, 4])
        self.assertEqual(result['proposals'][1]['raw_ocr_text'], 'POT 125')
        self.assertGreater(result['proposals'][1]['tesseract_mean_word_confidence_uncalibrated'], 0.5)
        self.assertTrue(result['requires_manual_review'])
        self.assertFalse(result['ready_for_equity_or_ev'])
        self.assertFalse(result['hands_reconstructed'])
        self.assertFalse(result['engine_confidence_is_calibrated_probability'])
        self.assertEqual(result['source_dense_refinement_sha256'], self.dense_sha)
        self.assertEqual(json.loads((self.out / 'roi_ocr_proposals.json').read_text()), result)
        for item in result['proposals']:
            self.assertEqual(item['status'], 'needs_manual_review')
            self.assertIsNone(item['parsed_candidate'])
            p = self.out / item['roi_png']
            self.assertTrue(p.is_file())
            self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(), item['roi_png_sha256'])
            self.assertGreater(p.stat().st_size, 0)

    def test_sparse_endpoint_supported(self):
        self.data['tasks'] = [dict(self.data['tasks'][0], frame_file=
                                   json.loads(self.changes.read_text())['candidate_intervals'][0]['previous_file'])]
        self.save()
        result = self.scan()
        self.assertEqual(result['proposals'][0]['frame_kind'], 'sparse')

    def test_odd_pixel_roi_preserves_exact_dimensions(self):
        self.data['tasks'] = [dict(self.data['tasks'][1],
                                   roi={'x': 1, 'y': 1, 'width': 101, 'height': 39})]
        self.save()
        result = self.scan()
        png = self.out / result['proposals'][0]['roi_png']
        probe = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
                                '-show_entries', 'stream=width,height', '-of', 'json',
                                str(png)], capture_output=True, text=True, check=True)
        stream = json.loads(probe.stdout)['streams'][0]
        self.assertEqual((stream['width'], stream['height']), (202, 78))

    def test_bad_manifest_sha_rejected(self):
        self.data['source_ingest_manifest_sha256'] = '0' * 64
        self.save()
        with self.assertRaisesRegex(ValueError, 'provenance'):
            self.scan()
        self.assertFalse(self.out.exists())

    def test_bad_dense_sha_rejected(self):
        self.data['source_dense_refinement_sha256'] = '0' * 64
        self.save()
        with self.assertRaisesRegex(ValueError, 'provenance'):
            self.scan()

    def test_duplicate_json_keys_rejected(self):
        self.tasks.write_text(self.tasks.read_text().replace('"schema_version": 1,',
                                                       '"schema_version": 1, "schema_version": 1,'))
        with self.assertRaisesRegex(ValueError, 'Duplicate JSON key'):
            self.scan()

    def test_nonfinite_json_rejected(self):
        self.tasks.write_text(self.tasks.read_text().replace('"width": 100', '"width": NaN'))
        with self.assertRaises(ValueError):
            self.scan()

    def test_roi_out_of_bounds_rejected(self):
        self.data['tasks'][0]['roi']['x'] = 300
        self.save()
        with self.assertRaisesRegex(ValueError, 'outside table'):
            self.scan()
        self.assertFalse(self.out.exists())

    def test_bool_coordinate_rejected(self):
        self.data['tasks'][0]['roi']['width'] = True
        self.save()
        with self.assertRaisesRegex(ValueError, 'coordinates'):
            self.scan()

    def test_wrong_table_id_rejected(self):
        self.data['tasks'][0]['table_id'] = 2
        self.save()
        with self.assertRaisesRegex(ValueError, 'identity'):
            self.scan()

    def test_path_traversal_rejected(self):
        self.data['tasks'][0]['frame_file'] = '../private.jpg'
        self.save()
        with self.assertRaisesRegex(ValueError, 'identity'):
            self.scan()

    def test_duplicate_task_rejected(self):
        self.data['tasks'].append(self.data['tasks'][0])
        self.save()
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            self.scan()

    def test_too_many_tasks_rejected(self):
        self.data['tasks'] *= 22
        self.save()
        with self.assertRaisesRegex(ValueError, 'provenance'):
            self.scan()

    def test_tampered_dense_frame_rejected(self):
        copied = self.case / 'refined'
        shutil.copytree(self.refined, copied)
        (copied / self.data['tasks'][0]['frame_file']).write_bytes(b'fake')
        with self.assertRaisesRegex(ValueError, 'modified'):
            self.scan(refined_dir=copied)
        self.assertFalse(self.out.exists())

    def test_symlink_dense_frame_rejected(self):
        copied = self.case / 'refined'
        shutil.copytree(self.refined, copied)
        path = copied / self.data['tasks'][0]['frame_file']
        path.unlink()
        path.symlink_to(self.refined / self.data['tasks'][0]['frame_file'])
        with self.assertRaisesRegex(ValueError, 'modified'):
            self.scan(refined_dir=copied)

    def test_tampered_sparse_frame_rejected(self):
        copied = self.case / 'ingest'
        shutil.copytree(self.ingest, copied)
        next(copied.glob('*.jpg')).write_bytes(b'fake')
        with self.assertRaisesRegex(ValueError, 'modified'):
            self.scan(ingest_dir=copied)

    def test_tampered_video_rejected(self):
        video = self.case / 'fake.mp4'
        shutil.copyfile(self.video, video)
        with video.open('ab') as f:
            f.write(b'tampered')
        with self.assertRaisesRegex(ValueError, 'Recording'):
            self.scan(recording=video)

    def test_tampered_regions_rejected(self):
        regions = self.case / 'regions.json'
        regions.write_text(self.regions.read_text() + ' ')
        with self.assertRaisesRegex(ValueError, 'region'):
            self.scan(regions_json=regions)

    def test_change_report_modified_rejected(self):
        changes = self.case / 'changes.json'
        changes.write_text(self.changes.read_text() + ' ')
        with self.assertRaisesRegex(ValueError, 'binding'):
            self.scan(changes_json=changes)

    def test_existing_output_rejected(self):
        self.out.mkdir()
        with self.assertRaisesRegex(ValueError, 'new and safe'):
            self.scan()

    def test_unsafe_output_inside_evidence_rejected(self):
        with self.assertRaisesRegex(ValueError, 'inside evidence'):
            self.scan(output_dir=self.refined / 'bad_output')

    def test_ocr_tsv_confidence_and_blank(self):
        header = b'level\ttext\tconf\n'
        self.assertEqual(parse_tsv(header), ('', 0, None))
        self.assertEqual(parse_tsv(header + b'5\tPOT\t80\n5\t123\t60\n'),
                         ('POT 123', 2, 0.7))
        with self.assertRaisesRegex(ValueError, 'Nonfinite'):
            parse_tsv(header + b'5\tPOT\tnan\n')
        with self.assertRaisesRegex(ValueError, 'engine scale'):
            parse_tsv(header + b'5\tPOT\t101\n')

    def test_invalid_dense_report_candidate_index_rejected(self):
        copied = self.case / 'refined'
        shutil.copytree(self.refined, copied)
        report = json.loads((copied / 'dense_refinement.json').read_text())
        report['refinements'][0]['source_candidate_index'] = 100
        (copied / 'dense_refinement.json').write_text(json.dumps(report))
        with self.assertRaisesRegex(ValueError, 'identity'):
            evidence_index(self.ingest, self.changes, copied)


if __name__ == '__main__':
    unittest.main()
