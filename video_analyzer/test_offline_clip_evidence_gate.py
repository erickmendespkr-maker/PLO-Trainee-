import unittest
from offline_clip_evidence_gate import classify_clip_evidence, REQUIRED


def complete():
    return dict(start_pts=12.0, end_pts=29.0, table_id=2,
                **{key: True for key in REQUIRED},
                ev_assumptions={'ranges': 'explicit', 'rake': 'zero', 'future_actions': 'none'})


class GateTests(unittest.TestCase):
    def test_complete(self):
        result = classify_clip_evidence(complete())
        self.assertEqual(result['status'], 'APPROVED_CONDITIONAL')
        self.assertTrue(result['can_attach_conditional_ev'])
        self.assertFalse(result['can_label_error'])

    def test_missing_each_field(self):
        for key in REQUIRED:
            with self.subTest(key=key):
                data = complete(); data[key] = None
                self.assertEqual(classify_clip_evidence(data)['status'], 'REVIEW_REQUIRED')

    def test_unreviewed_false(self):
        data = complete(); data['hand_verified'] = False
        self.assertIn('hand_verified', classify_clip_evidence(data)['missing_evidence'])

    def test_model_missing(self):
        data = complete(); data['ev_assumptions'] = {}
        self.assertEqual(classify_clip_evidence(data)['status'], 'INSUFFICIENT_MODEL')

    def test_bad_timestamps(self):
        for a, b in [(3, 3), (5, 4), (-1, 5), (0, float('nan')), (0, float('inf')), ('0', 2)]:
            with self.subTest(a=a, b=b):
                data = complete(); data['start_pts'] = a; data['end_pts'] = b
                with self.assertRaises(ValueError): classify_clip_evidence(data)

    def test_table_bounds(self):
        for table in (0, 5, True, '2'):
            data = complete(); data['table_id'] = table
            with self.assertRaises(ValueError): classify_clip_evidence(data)

    def test_invalid_record(self):
        with self.assertRaises(ValueError): classify_clip_evidence(None)


if __name__ == '__main__': unittest.main()
