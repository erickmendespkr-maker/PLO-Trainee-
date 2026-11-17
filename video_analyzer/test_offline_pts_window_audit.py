import unittest
from offline_pts_window_audit import audit_transition_windows


def sample(**changes):
    item = dict(table_id='table-1', earliest_pts=1., latest_pts=3.,
                gap_seconds=2., requires_review=True, usable_as_hand_boundary=False,
                status='CANDIDATE', start_frame_sha256='a'*64, end_frame_sha256='b'*64)
    item.update(changes)
    return item


class AuditTests(unittest.TestCase):
    def test_valid(self):
        result = audit_transition_windows([sample()], video_duration_seconds=10)
        self.assertEqual(result['verified_hands'], 0)
        self.assertIsNone(result['review_queue'][0]['hand_id'])

    def test_empty(self):
        self.assertEqual(audit_transition_windows([], video_duration_seconds=10)['candidate_windows'], 0)

    def test_sparse(self):
        self.assertEqual(audit_transition_windows([sample(status='SPARSE_UNCERTAIN')], video_duration_seconds=10)['sparse_windows'], 1)

    def test_order(self):
        result = audit_transition_windows([sample(earliest_pts=4., latest_pts=6.), sample()], video_duration_seconds=10)
        self.assertEqual(result['review_queue'][0]['source_index'], 1)

    def test_promoted_rejected(self):
        with self.assertRaises(ValueError):
            audit_transition_windows([sample(usable_as_hand_boundary=True)], video_duration_seconds=10)

    def test_outside_video(self):
        with self.assertRaises(ValueError):
            audit_transition_windows([sample()], video_duration_seconds=2)

    def test_bad_hash(self):
        with self.assertRaises(ValueError):
            audit_transition_windows([sample(start_frame_sha256='x'*64)], video_duration_seconds=10)

    def test_bad_gap(self):
        with self.assertRaises(ValueError):
            audit_transition_windows([sample(gap_seconds=4)], video_duration_seconds=10)

    def test_table_limit(self):
        with self.assertRaises(ValueError):
            audit_transition_windows([sample(table_id=f't{i}') for i in range(5)], video_duration_seconds=10)

    def test_boolean_duration(self):
        with self.assertRaises(ValueError):
            audit_transition_windows([], video_duration_seconds=True)


if __name__ == '__main__':
    unittest.main()
