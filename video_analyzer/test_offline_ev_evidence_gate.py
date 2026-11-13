import unittest
from .offline_ev_evidence_gate import gate_ev_report

H = 'a' * 64
R = {'video_sha256': H, 'review_status': 'CONFIRMED', 'table_id': 2,
     'hand_id': 'hand-1', 'start_seconds': 10, 'end_seconds': 20}
E = {'gto_solution': False, 'visual_hand_verified_by_this_module': False,
     'publication_requires_external_review_binding': True,
     'status': 'RANGE_SENSITIVE', 'unit': 'bb', 'assumptions': {'range': 'hypothetical'},
     'scenario_ids': ['tight', 'loose'],
     'interval_type': 'hypothetical_model_bounds_not_statistical_confidence',
     'chosen_action': 'call', 'reviewed_hand_claimed_by_caller': True}


class EvidenceGateTests(unittest.TestCase):
    def check_rejected(self, *, review=None, report=None, hash=H, reason):
        result = gate_ev_report(E if report is None else report,
                                R if review is None else review,
                                trusted_video_sha256=hash)
        self.assertFalse(result['approved'])
        self.assertIn(reason, result['reasons'])
        self.assertEqual(result['status'], 'INSUFFICIENT_DATA')

    def test_valid_consistency(self):
        result = gate_ev_report(E, R, trusted_video_sha256=H)
        self.assertTrue(result['approved'])
        self.assertEqual(result['status'], 'CONDITIONAL_MODEL_ONLY')

    def test_wrong_video(self):
        self.check_rejected(hash='b'*64, reason='recording_hash_mismatch')

    def test_unreviewed(self):
        self.check_rejected(review={**R, 'review_status': 'PENDING'}, reason='hand_not_confirmed')

    def test_invalid_table(self):
        self.check_rejected(review={**R, 'table_id': 5}, reason='invalid_table_id')

    def test_invalid_timestamp(self):
        self.check_rejected(review={**R, 'start_seconds': float('nan')}, reason='invalid_time_range')

    def test_claimed_gto(self):
        self.check_rejected(report={**E, 'gto_solution': True}, reason='unsupported_verification_claim')

    def test_missing_assumptions(self):
        self.check_rejected(report={**E, 'assumptions': {}}, reason='missing_model_context')

    def test_false_review_claim(self):
        self.check_rejected(report={**E, 'reviewed_hand_claimed_by_caller': False},
                            reason='caller_has_not_claimed_review')

    def test_missing_scenarios(self):
        self.check_rejected(report={**E, 'scenario_ids': []}, reason='missing_scenarios')

    def test_no_mutation(self):
        report, review = E.copy(), R.copy()
        gate_ev_report(E, R, trusted_video_sha256=H)
        self.assertEqual(E, report)
        self.assertEqual(R, review)
