import copy
import unittest
from .offline_ev_report_identity import bind_report

SHA = 'a' * 64
IDENTITY = {'hand_id': 'h1', 'table_id': 2, 'video_sha256': SHA,
            'start_seconds': 10, 'end_seconds': 25}
REVIEW = {**IDENTITY, 'review_status': 'CONFIRMED'}
REPORT = {'hand_identity': IDENTITY, 'status': 'RANGE_SENSITIVE',
          'gto_solution': False, 'visual_hand_verified_by_this_module': False,
          'assumptions': {'range': 'hypothetical'}}


class IdentityTests(unittest.TestCase):
    def test_match_is_not_approval(self):
        result = bind_report(REPORT, REVIEW)
        self.assertFalse(result['approved_for_publication'])
        self.assertEqual(len(result['report_sha256']), 64)

    def test_deterministic_hash(self):
        report = dict(reversed(list(REPORT.items())))
        self.assertEqual(bind_report(report, REVIEW)['report_sha256'], bind_report(REPORT, REVIEW)['report_sha256'])

    def test_swapped_hand(self):
        r = copy.deepcopy(REPORT); r['hand_identity']['hand_id'] = 'h2'
        with self.assertRaises(ValueError): bind_report(r, REVIEW)

    def test_swapped_table(self):
        r = copy.deepcopy(REPORT); r['hand_identity']['table_id'] = 3
        with self.assertRaises(ValueError): bind_report(r, REVIEW)

    def test_swapped_video(self):
        r = copy.deepcopy(REPORT); r['hand_identity']['video_sha256'] = 'b'*64
        with self.assertRaises(ValueError): bind_report(r, REVIEW)

    def test_swapped_time(self):
        r = copy.deepcopy(REPORT); r['hand_identity']['end_seconds'] = 26
        with self.assertRaises(ValueError): bind_report(r, REVIEW)

    def test_unconfirmed(self):
        with self.assertRaises(ValueError): bind_report(REPORT, {**REVIEW, 'review_status': 'PENDING'})

    def test_nan_rejected(self):
        r = copy.deepcopy(REPORT); r['assumptions']['x'] = float('nan')
        with self.assertRaises(ValueError): bind_report(r, REVIEW)

    def test_bool_table_rejected(self):
        r = copy.deepcopy(REPORT); r['hand_identity']['table_id'] = True
        with self.assertRaises(ValueError): bind_report(r, REVIEW)

    def test_gto_claim_rejected(self):
        with self.assertRaises(ValueError): bind_report({**REPORT, 'gto_solution': True}, REVIEW)

    def test_no_visual_claim(self):
        with self.assertRaises(ValueError): bind_report({**REPORT, 'visual_hand_verified_by_this_module': True}, REVIEW)

    def test_report_changes_hash(self):
        r = copy.deepcopy(REPORT); r['assumptions']['range'] = 'different'
        self.assertNotEqual(bind_report(r, REVIEW)['report_sha256'], bind_report(REPORT, REVIEW)['report_sha256'])


if __name__ == '__main__':
    unittest.main()
