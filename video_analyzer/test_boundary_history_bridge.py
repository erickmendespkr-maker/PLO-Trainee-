"""Synthetic four-table bridge tests; not real poker validation."""
import copy
import unittest
from boundary_history_bridge import build


def fixture():
    tasks, rows = [], []
    for table in range(1, 5):
        for i, sec in enumerate((1., 3.)):
            tid = f'table_{table:02d}_window_{i:04d}'
            tasks.append({'task_id': tid, 'table_id': table,
                          'window_start_seconds': sec, 'window_end_seconds': sec + .2,
                          'frames': [{'frame_id': i, 'pts_byte_matched': True}]})
            rows.append({'task_id': tid, 'verdict_reported_by_human': 'confirmed_transition',
                         'timestamp_reported_by_human': sec + .1,
                         'frame_ids': [i], 'independently_verified': False})
    false = dict.fromkeys(('hand_boundaries_verified', 'cards_or_actions_verified',
                           'ready_for_equity_or_ev', 'automatic_clip_selection_authorized',
                           'strategic_error_established'), False)
    packet = {'analysis_status': 'candidate_boundary_review_only',
              'recording_sha256': 'a'*64, 'tasks': tasks, **false}
    labels = {'analysis_status': 'unverified_human_boundary_labels',
              'packet_sha256': 'b'*64, 'annotations': rows, **false}
    return packet, labels


class BridgeTests(unittest.TestCase):
    def test_four_tables_no_math_claims(self):
        packet, labels = fixture()
        result = build(packet, labels, 'b'*64)
        self.assertEqual(len(result['candidate_spans']), 4)
        self.assertFalse(result['ready_for_equity_or_ev'])
        self.assertTrue(all(s['cards'] is None and s['ev'] is None for s in result['candidate_spans']))

    def test_reject_unmatched_pts(self):
        packet, labels = fixture()
        packet['tasks'][0]['frames'][0]['pts_byte_matched'] = False
        with self.assertRaises(ValueError):
            build(packet, labels, 'b'*64)

    def test_reject_wrong_sha(self):
        packet, labels = fixture()
        with self.assertRaises(ValueError):
            build(packet, labels, 'c'*64)

    def test_reject_overlap(self):
        packet, labels = fixture()
        packet['tasks'][1]['window_start_seconds'] = 1.15
        with self.assertRaises(ValueError):
            build(packet, labels, 'b'*64)

    def test_reject_false_authority(self):
        packet, labels = fixture()
        labels['ready_for_equity_or_ev'] = True
        with self.assertRaises(ValueError):
            build(packet, labels, 'b'*64)


class UpstreamFFmpegIntegration(unittest.TestCase):
    """Real FFmpeg on synthetic frames; not real poker OCR validation."""
    @classmethod
    def setUpClass(cls):
        import test_activity_boundary_review_handoff as upstream
        cls.upstream = upstream
        upstream.ReviewHandoffTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        cls.upstream.ReviewHandoffTests.tearDownClass()

    def test_packet_human_labels_bridge(self):
        import hashlib
        import json
        from pathlib import Path
        import tempfile
        from activity_boundary_review_handoff import packet, annotate
        from boundary_history_bridge import export
        u = self.upstream.ReviewHandoffTests
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            p = root / 'packet.json'
            report = packet(u.video, u.temporal, u.boundary, u.evidence,
                            u.audit, p, u.regions)
            form = {'schema_version': 1,
                    'packet_sha256': hashlib.sha256(p.read_bytes()).hexdigest(),
                    'annotations': []}
            for task in report['tasks']:
                form['annotations'].append({
                    'task_id': task['task_id'], 'verdict': 'confirmed_transition',
                    'reviewer': 'synthetic', 'timestamp_seconds': task['window_start_seconds'],
                    'frame_ids': [task['frames'][0]['frame_id']], 'notes': ''})
            f = root / 'form.json'
            f.write_text(json.dumps(form))
            labels = root / 'labels.json'
            annotate(p, f, labels)
            result = export(p, labels, root / 'bridge.json')
            self.assertEqual(len(result['candidate_spans']), 0)
            self.assertFalse(result['ready_for_equity_or_ev'])


if __name__ == '__main__':
    unittest.main()
