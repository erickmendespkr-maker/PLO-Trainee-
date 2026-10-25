"""Offline synthetic four-table tests for the human review handoff."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from activity_boundary_review_handoff import packet, template, annotate, digest
from activity_ocr_boundary_triage import build_ocr_boundary_triage
from activity_ocr_boundary_visual_evidence import export_boundary_visual_evidence
from activity_ocr_boundary_pts_audit import audit_ocr_boundary_pts
from test_activity_ocr_boundary_triage import report, change, A, B


class ReviewHandoffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        cls.video = root / 'synthetic.mp4'
        subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
                        '-f', 'lavfi', '-i', 'testsrc=size=320x240:rate=5:duration=4',
                        '-c:v', 'mpeg4', '-y', str(cls.video)],
                       check=True, capture_output=True, timeout=30)
        temporal = report(*(change('hero_cards', A, B, table=i) for i in range(1, 5)))
        temporal['recording_sha256'] = digest(cls.video)
        cls.temporal = root / 'temporal.json'
        cls.temporal.write_text(json.dumps(temporal))
        cls.boundary = root / 'boundary.json'
        cls.boundary.write_text(json.dumps(build_ocr_boundary_triage(
            temporal, source_sha256=digest(cls.temporal))))
        cls.regions = root / 'regions.json'
        cls.regions.write_text(json.dumps({str(i): {
            'x': ((i - 1) % 2) * 160, 'y': ((i - 1) // 2) * 120,
            'width': 160, 'height': 120} for i in range(1, 5)}))
        cls.evidence = root / 'navigation'
        export_boundary_visual_evidence(cls.video, cls.temporal, cls.boundary,
                                        cls.evidence, regions_json=cls.regions,
                                        samples_per_window=1)
        cls.audit_dir = root / 'audit'
        audit_ocr_boundary_pts(cls.video, cls.temporal, cls.boundary,
                               cls.evidence, cls.audit_dir, regions_json=cls.regions)
        cls.audit = cls.audit_dir / 'boundary_pts_audit.json'

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.output = self.root / 'packet.json'

    def build(self):
        return packet(self.video, self.temporal, self.boundary, self.evidence,
                      self.audit, self.output, self.regions)

    def test_four_tables_and_no_math_claims(self):
        result = self.build()
        self.assertEqual(result['counts'], {'tasks': 4, 'with_frames': 4})
        self.assertEqual({x['table_id'] for x in result['tasks']}, {1, 2, 3, 4})
        self.assertTrue(all(t['frames'][0]['pts_byte_matched'] for t in result['tasks']))
        self.assertFalse(result['ready_for_equity_or_ev'])
        self.assertFalse(result['hand_boundaries_verified'])

    def test_rejects_tampered_audit(self):
        altered = self.root / 'altered.json'
        data = json.loads(self.audit.read_text())
        data['frames'][0]['decoded_pts_seconds'] = 100
        altered.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'independent re-decode'):
            packet(self.video, self.temporal, self.boundary, self.evidence,
                   altered, self.output, self.regions)

    def test_annotations_are_not_verified(self):
        result = self.build()
        form = self.root / 'form.json'
        template(self.output, form)
        data = json.loads(form.read_text())
        data['annotations'] = [{
            'task_id': result['tasks'][0]['task_id'], 'verdict': 'uncertain',
            'reviewer': 'synthetic', 'timestamp_seconds': None,
            'frame_ids': [result['tasks'][0]['frames'][0]['frame_id']],
            'notes': 'Synthetic only'}]
        form.write_text(json.dumps(data))
        labels = annotate(self.output, form, self.root / 'labels.json')
        self.assertEqual(labels['pending'], 3)
        self.assertFalse(labels['hand_boundaries_verified'])
        self.assertFalse(labels['annotations'][0]['independently_verified'])

    def test_confirmed_requires_timestamp_and_frame(self):
        result = self.build()
        form = self.root / 'form.json'
        template(self.output, form)
        data = json.loads(form.read_text())
        data['annotations'] = [{
            'task_id': result['tasks'][0]['task_id'], 'verdict': 'confirmed_transition',
            'reviewer': 'synthetic', 'timestamp_seconds': 3.8,
            'frame_ids': [], 'notes': ''}]
        form.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            annotate(self.output, form, self.root / 'labels.json')

    def test_overwrite_refused(self):
        self.build()
        with self.assertRaises(ValueError):
            self.build()


if __name__ == '__main__':
    unittest.main()
