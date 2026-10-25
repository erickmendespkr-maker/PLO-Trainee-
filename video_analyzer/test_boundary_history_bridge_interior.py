"""Synthetic interior OCR candidate preservation and adversarial inputs."""
import copy
import unittest
from test_boundary_history_bridge import fixture
from boundary_history_bridge import build

class InteriorEvidenceTests(unittest.TestCase):
    """Deterministic synthetic candidates; no strategic claims."""

    def setUp(self):
        self.packet, self.labels = fixture()
        self.packet['tasks'] = self.packet['tasks'][:2]
        self.labels['annotations'] = self.labels['annotations'][:2]

    def add_interior(self, tid='interior', start=1.5, end=1.7):
        self.packet['tasks'].append({
            'task_id': tid, 'table_id': 1,
            'window_start_seconds': start, 'window_end_seconds': end,
            'frames': [{'frame_id': 9, 'pts_byte_matched': True,
                        'png_sha256': 'a'*64, 'decoded_pts_seconds': 1.6}]})

    def test_pending_interior_is_retained(self):
        self.add_interior()
        result = build(self.packet, self.labels, 'b'*64)
        span = result['candidate_spans'][0]
        self.assertEqual(span['interior_candidates'][0]['review_status'], 'pending')
        self.assertTrue(span['contains_unresolved_interior_candidates'])
        self.assertEqual(result['counts']['pending'], 1)
        self.assertFalse(result['ready_for_equity_or_ev'])
        self.assertEqual(len(span['boundary_evidence']), 2)
        self.assertTrue(span['boundary_evidence'][0]['frame_provenance'][0]['pts_byte_matched'])
        self.assertFalse(span['boundary_evidence'][0]['independently_verified'])

    def test_uncertain_and_rejected_are_retained_distinctly(self):
        self.add_interior()
        self.labels['annotations'].append({
            'task_id': 'interior', 'verdict_reported_by_human': 'uncertain',
            'timestamp_reported_by_human': None, 'frame_ids': [9],
            'independently_verified': False})
        span = build(self.packet, self.labels, 'b'*64)['candidate_spans'][0]
        self.assertTrue(span['contains_unresolved_interior_candidates'])
        self.assertEqual(span['interior_candidates'][0]['reviewed_frame_provenance'][0]['png_sha256'], 'a'*64)
        self.labels['annotations'][-1]['verdict_reported_by_human'] = 'rejected_transition'
        span = build(self.packet, self.labels, 'b'*64)['candidate_spans'][0]
        self.assertFalse(span['contains_unresolved_interior_candidates'])
        self.assertEqual(span['interior_candidates'][0]['review_status'], 'rejected_transition')

    def test_interleaved_four_table_isolation(self):
        packet, labels = fixture()
        for table in range(1, 5):
            packet['tasks'].append({'task_id': 'pending'+str(table), 'table_id': table,
                                    'window_start_seconds': 1.5, 'window_end_seconds': 1.6,
                                    'frames': []})
        spans = build(packet, labels, 'b'*64)['candidate_spans']
        self.assertEqual([s['table_id'] for s in spans], [1, 2, 3, 4])
        for span in spans:
            self.assertEqual(span['interior_candidates'][0]['task_id'],
                             'pending'+str(span['table_id']))

    def test_reject_bad_pending_count(self):
        self.add_interior()
        self.labels['pending'] = 0
        with self.assertRaises(ValueError):
            build(self.packet, self.labels, 'b'*64)

    def test_reject_unconfirmed_timestamp(self):
        self.add_interior()
        self.labels['annotations'].append({
            'task_id': 'interior', 'verdict_reported_by_human': 'uncertain',
            'timestamp_reported_by_human': 1.6, 'frame_ids': [9],
            'independently_verified': False})
        with self.assertRaises(ValueError):
            build(self.packet, self.labels, 'b'*64)

    def test_reject_duplicate_frame_ids(self):
        self.packet['tasks'][0]['frames'].append(copy.deepcopy(self.packet['tasks'][0]['frames'][0]))
        with self.assertRaises(ValueError):
            build(self.packet, self.labels, 'b'*64)

    def test_reject_bad_table_and_nonfinite_windows(self):
        self.packet['tasks'][0]['table_id'] = True
        with self.assertRaises(ValueError):
            build(self.packet, self.labels, 'b'*64)
        self.packet['tasks'][0]['table_id'] = 1
        self.packet['tasks'][0]['window_start_seconds'] = float('nan')
        with self.assertRaises(ValueError):
            build(self.packet, self.labels, 'b'*64)

    def test_reject_unknown_verdict(self):
        self.labels['annotations'][0]['verdict_reported_by_human'] = 'trusted'
        with self.assertRaises(ValueError):
            build(self.packet, self.labels, 'b'*64)

    def test_reject_duplicate_json_keys_without_output(self):
        import tempfile
        from pathlib import Path
        from boundary_history_bridge import export
        with tempfile.TemporaryDirectory() as d:
            p, l, out = (Path(d)/n for n in ('packet.json','labels.json','out.json'))
            p.write_text('{"schema_version":1,"schema_version":1}')
            l.write_text('{}')
            with self.assertRaises(ValueError):
                export(p, l, out)
            self.assertFalse(out.exists())

    def test_export_prevents_overwrite_and_roundtrips(self):
        import tempfile
        import json
        from pathlib import Path
        from boundary_history_bridge import export
        self.add_interior()
        with tempfile.TemporaryDirectory() as d:
            p, l, out = (Path(d)/n for n in ('packet.json','labels.json','out.json'))
            raw = json.dumps(self.packet).encode()
            p.write_bytes(raw)
            self.labels['packet_sha256'] = __import__('hashlib').sha256(raw).hexdigest()
            l.write_text(json.dumps(self.labels))
            result = export(p, l, out)
            self.assertEqual(json.loads(out.read_text()), result)
            with self.assertRaises(ValueError):
                export(p, l, out)
