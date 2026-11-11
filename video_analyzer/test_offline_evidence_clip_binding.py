"""Synthetic, no video needed: offline clip provenance contract."""
import json
from pathlib import Path
import tempfile
import unittest
import offline_evidence_clip_binding as mod

class BindingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.gate = {
            'schema_version': 1, 'status': 'matching_claims_not_independently_verified',
            'source_hand_reconstruction_verified': False,
            'equity_ranges_observed_from_video': False,
            'ready_for_strategic_verdict': False,
            'automatic_clip_selection_authorized': False,
            'pot_call_values_match': True, 'annotation_sha256': 'a'*64,
            'scenario_sha256': 'b'*64, 'source_video_sha256_claim': 'c'*64,
            'hand_id_claim': 'hand_1', 'table_id_claim': 2,
            'hand_interval_seconds_claim': [15., 22.], 'scenario_id': 'sample'}
        self.clip = {
            'schema_version': 1, 'analysis_status': 'manually_selected_offline_clip',
            'video_evidence_verified': False,
            'automatic_clip_selection_authorized': False, 'audio_included': False,
            'source_video_sha256': 'c'*64, 'source_request_sha256': 'd'*64,
            'clip_sha256': 'e'*64, 'hand_id': 'hand_1', 'table_id': 2,
            'start_seconds': 14., 'end_seconds': 23.}
        self.gp = self.root/'gate.json'
        self.cp = self.root/'clip.json'
        self.out = self.root/'binding.json'
        self.write()
    def write(self):
        self.gp.write_text(json.dumps(self.gate))
        self.cp.write_text(json.dumps(self.clip))
    def reject(self):
        self.write()
        with self.assertRaises(ValueError):
            mod.run(self.gp, self.cp, self.out)
    def test_valid_and_provenance(self):
        result = mod.run(self.gp, self.cp, self.out)
        self.assertTrue(result['clip_contains_claimed_hand_interval'])
        self.assertFalse(result['video_evidence_verified'])
        self.assertFalse(result['ready_for_strategic_verdict'])
        self.assertEqual(result['gate_sha256'], mod.digest(self.gp))
        self.assertEqual(json.loads(self.out.read_text()), result)
    def test_refuse_overwrite(self):
        mod.run(self.gp, self.cp, self.out)
        with self.assertRaises(ValueError):
            mod.run(self.gp, self.cp, self.out)
    def test_other_video(self):
        self.clip['source_video_sha256'] = 'f'*64
        self.reject()
    def test_other_hand(self):
        self.clip['hand_id'] = 'another'
        self.reject()
    def test_other_table(self):
        self.clip['table_id'] = 3
        self.reject()
    def test_partial_clip_start(self):
        self.clip['start_seconds'] = 16
        self.reject()
    def test_partial_clip_end(self):
        self.clip['end_seconds'] = 21
        self.reject()
    def test_boundary_exact(self):
        self.clip['start_seconds'] = 15
        self.clip['end_seconds'] = 22
        self.write()
        self.assertTrue(mod.run(self.gp, self.cp, self.out)['clip_contains_claimed_hand_interval'])
    def test_invalid_hand_interval(self):
        self.gate['hand_interval_seconds_claim'] = [23,15]
        self.reject()
    def test_bad_hash(self):
        self.gate['scenario_sha256'] = 'xyz'
        self.reject()
    def test_promoted_video(self):
        self.clip['video_evidence_verified'] = True
        self.reject()
    def test_promoted_gate(self):
        self.gate['ready_for_strategic_verdict'] = True
        self.reject()
    def test_auto_selection(self):
        self.gate['automatic_clip_selection_authorized'] = True
        self.reject()
    def test_bool_timestamp(self):
        self.clip['start_seconds'] = False
        self.reject()
    def test_duplicate_keys(self):
        self.gp.write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaises(ValueError):
            mod.run(self.gp, self.cp, self.out)
    def test_nan(self):
        self.gp.write_text('{"x":NaN}')
        with self.assertRaises(ValueError):
            mod.run(self.gp, self.cp, self.out)
    def test_non_json(self):
        self.gp.write_text('broken')
        with self.assertRaises(ValueError):
            mod.run(self.gp, self.cp, self.out)
    def test_wrong_schema(self):
        self.gate['schema_version'] = True
        self.reject()

if __name__ == '__main__':
    unittest.main(verbosity=2)
