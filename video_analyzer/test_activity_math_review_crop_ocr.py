"""Synthetic-only integration tests for PTS-audited table OCR probes."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from activity_hand_review_packet import build_hand_review_packet
from activity_math_readiness_triage import build_math_readiness_triage
from activity_math_review_handoff import build_math_review_handoff
from activity_math_review_frames import export_math_review_frames
from activity_math_review_pts_audit import audit_math_review_pts
from activity_math_review_table_stills import export_math_review_table_stills
from activity_math_review_crop_ocr import export_math_review_crop_ocr
from test_activity_consistency_frame_review import changed


@unittest.skipUnless(all(shutil.which(x) for x in ('ffmpeg', 'ffprobe', 'tesseract')),
                     'FFmpeg, ffprobe, and Tesseract required')
class CropOCRTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.video = cls.root / 'synthetic.mp4'
        subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
                        '-f', 'lavfi', '-i', 'testsrc2=size=320x240:rate=7:duration=5',
                        '-c:v', 'mpeg4', '-y', str(cls.video)], check=True, capture_output=True)
        sha = hashlib.sha256(cls.video.read_bytes()).hexdigest()
        queue, timeline = changed()
        queue['recording_sha256'] = sha
        timeline['recording_sha256'] = sha
        packet = build_hand_review_packet(queue, timeline)
        triage = build_math_readiness_triage(packet, timeline)
        handoff = build_math_review_handoff(triage, packet, timeline)
        cls.sources = []
        for name, data in [('handoff', handoff), ('triage', triage),
                           ('packet', packet), ('timeline', timeline)]:
            path = cls.root / (name + '.json')
            path.write_text(json.dumps(data))
            cls.sources.append(path)
        cls.frames = cls.root / 'frames'
        export_math_review_frames(cls.video, *cls.sources, cls.frames)
        cls.regions = cls.root / 'regions.json'
        cls.regions.write_text(json.dumps({'schema_version': 1, 'layout': 'grid',
                                           'rows': 2, 'columns': 2}))
        cls.tables = cls.root / 'tables'
        export_math_review_table_stills(cls.video, cls.frames, *cls.sources,
                                        cls.regions, cls.tables)
        cls.pts = cls.root / 'pts'
        audit_math_review_pts(cls.video, cls.frames, *cls.sources, cls.pts)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.tmp2 = tempfile.TemporaryDirectory(dir=self.root)
        self.work = Path(self.tmp2.name)
        self.rois = self.work / 'rois.json'
        self.rois.write_text(json.dumps({'schema_version': 1, 'rois': [
            {'table_id': i, 'field': 'pot', 'x': 0, 'y': 0, 'width': 80, 'height': 60}
            for i in range(1, 5)]}))

    def tearDown(self):
        self.tmp2.cleanup()

    def run_export(self, name='out', **kwargs):
        return export_math_review_crop_ocr(
            self.video, self.frames, *self.sources, self.regions,
            kwargs.pop('table_dir', self.tables), kwargs.pop('pts_dir', self.pts),
            self.rois, self.work / name, **kwargs)

    def test_four_tables_and_verified_pts_with_no_math_authority(self):
        report = self.run_export()
        self.assertEqual(report['counts']['ocr_probes'], 4)
        self.assertEqual(report['counts']['with_verified_decoded_pts'], 4)
        self.assertEqual({c['table_id'] for c in report['candidates']}, {1, 2, 3, 4})
        self.assertTrue(all(c['requires_manual_review'] for c in report['candidates']))
        self.assertTrue(all(c['decoded_pts_verified_by_identical_png'] for c in report['candidates']))
        self.assertFalse(report['ready_for_equity_or_ev'])
        self.assertFalse(report['automatic_clip_selection_authorized'])
        self.assertEqual(json.loads((self.work / 'out' / 'math_review_crop_ocr.json').read_text()), report)
        with self.assertRaises(ValueError):
            self.run_export()

    def test_invalid_roi_rejected_without_output(self):
        invalid = [
            {'table_id': 1, 'field': 'pot', 'x': 120, 'y': 0, 'width': 80, 'height': 60},
            {'table_id': 1, 'field': 'bad', 'x': 0, 'y': 0, 'width': 80, 'height': 60},
            {'table_id': True, 'field': 'pot', 'x': 0, 'y': 0, 'width': 80, 'height': 60},
        ]
        for i, row in enumerate(invalid):
            with self.subTest(i=i):
                self.rois.write_text(json.dumps({'schema_version': 1, 'rois': [row]}))
                with self.assertRaises(ValueError):
                    self.run_export(f'bad_{i}')
                self.assertFalse((self.work / f'bad_{i}').exists())

    def test_duplicate_roi_and_budget_rejected(self):
        rois = json.loads(self.rois.read_text())
        rois['rois'].append(dict(rois['rois'][0]))
        self.rois.write_text(json.dumps(rois))
        with self.assertRaises(ValueError):
            self.run_export()
        self.rois.write_text(json.dumps({'schema_version': 1, 'rois': rois['rois'][:4]}))
        with self.assertRaises(ValueError):
            self.run_export(max_tasks=3)
        self.assertFalse((self.work / 'out').exists())

    def test_tampered_crop_rejected(self):
        alt = self.work / 'altered'
        shutil.copytree(self.tables, alt)
        crop = next(alt.glob('table_*.png'))
        crop.write_bytes(crop.read_bytes() + b'tamper')
        with self.assertRaises(ValueError):
            self.run_export(table_dir=alt)
        self.assertFalse((self.work / 'out').exists())

    def test_forged_pts_report_rejected(self):
        alt = self.work / 'fake_pts'
        shutil.copytree(self.pts, alt)
        path = alt / 'math_review_pts_audit.json'
        report = json.loads(path.read_text())
        report['frames'][0]['decoded_frame_pts_seconds'] = 999.0
        path.write_text(json.dumps(report))
        with self.assertRaises(ValueError):
            self.run_export(pts_dir=alt)
        self.assertFalse((self.work / 'out').exists())

    def test_symlink_and_cli(self):
        alias = self.work / 'alias'
        alias.symlink_to(self.tables, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.run_export(table_dir=alias)
        command = [sys.executable, str(Path(__file__).with_name('activity_math_review_crop_ocr.py')),
                   str(self.video), str(self.frames), *map(str, self.sources),
                   str(self.regions), str(self.tables), str(self.pts), str(self.rois),
                   str(self.work / 'cli')]
        run = subprocess.run(command, capture_output=True, text=True, timeout=120)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)['ocr_probes'], 4)


if __name__ == '__main__':
    unittest.main()
