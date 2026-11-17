"""Synthetic regression tests for offline PTS review handoff."""
import unittest
from offline_pts_review_handoff import build_pts_review_handoff

H = 'a' * 64


def obs(table, pts, state, sha='b' * 64):
    return {'table_id': table, 'pts': pts, 'state': state, 'frame_sha256': sha}


class HandoffTests(unittest.TestCase):
    def build(self, rows, **kwargs):
        return build_pts_review_handoff(rows, video_sha256=H,
                                        video_duration_seconds=100, **kwargs)

    def test_valid_transition_pending(self):
        result = self.build([obs('t1', 1, 'a'), obs('t1', 3, 'b')])
        self.assertEqual(result['audit']['candidate_windows'], 1)
        self.assertEqual(result['tasks'][0]['review_status'], 'PENDING')
        self.assertFalse(result['tasks'][0]['strategic_commentary_allowed'])
        self.assertIsNone(result['tasks'][0]['verified_hand_id'])

    def test_deterministic_across_input_order(self):
        rows = [obs('t1', 1, 'a'), obs('t1', 3, 'b'), obs('t2', 2, 'c'), obs('t2', 4, 'd')]
        self.assertEqual(self.build(rows), self.build(list(reversed(rows))))

    def test_no_transitions(self):
        self.assertEqual(self.build([obs('t1', 1, 'a'), obs('t1', 3, 'a')])['tasks'], [])

    def test_sparse_window(self):
        result = self.build([obs('t1', 1, 'a'), obs('t1', 80, 'b')])
        self.assertEqual(result['tasks'][0]['evidence']['status'], 'SPARSE_UNCERTAIN')

    def test_out_of_video_rejected(self):
        with self.assertRaises(ValueError):
            self.build([obs('t1', 101, 'a')])

    def test_too_many_tables_without_transitions(self):
        with self.assertRaises(ValueError):
            self.build([obs(f't{i}', 1, 'a') for i in range(5)])

    def test_bad_video_hash(self):
        with self.assertRaises(ValueError):
            build_pts_review_handoff([], video_sha256='invalid', video_duration_seconds=100)

    def test_duplicate_pts(self):
        with self.assertRaises(ValueError):
            self.build([obs('t1', 1, 'a'), obs('t1', 1, 'b')])

    def test_bad_duration(self):
        with self.assertRaises(ValueError):
            build_pts_review_handoff([], video_sha256=H, video_duration_seconds=float('nan'))

    def test_provenance_changes_review_id(self):
        rows = [obs('t1', 1, 'a'), obs('t1', 3, 'b')]
        first = self.build(rows)['tasks'][0]['review_id']
        second = build_pts_review_handoff(rows, video_sha256='c'*64,
                                          video_duration_seconds=100)['tasks'][0]['review_id']
        self.assertNotEqual(first, second)


if __name__ == '__main__':
    unittest.main()
