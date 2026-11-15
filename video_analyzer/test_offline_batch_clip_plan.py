import tempfile
import unittest
from pathlib import Path
from offline_batch_clip_plan import plan_review_exports


def handoff():
    return {'schema_version': 1, 'type': 'provisional_clip_export_handoff',
            'source_duration_seconds': 20, 'human_review_required': True,
            'gto_solution': False, 'windows': [
                {'table_id': 1, 'start_pts': 1, 'end_pts': 3,
                 'candidate_ids': ['a'], 'hand_boundary_verified': False,
                 'human_review_required': True, 'export_approved': False,
                 'gto_solution': False, 'strategic_conclusion': None},
                {'table_id': 2, 'start_pts': 4, 'end_pts': 7,
                 'candidate_ids': ['b'], 'hand_boundary_verified': False,
                 'human_review_required': True, 'export_approved': False,
                 'gto_solution': False, 'strategic_conclusion': None}]}


class TestBatchPlan(unittest.TestCase):
    def test_two_tables_remain_unverified(self):
        with tempfile.TemporaryDirectory() as d:
            plan = plan_review_exports(handoff(), d)
            self.assertEqual(len(plan), 2)
            self.assertEqual([p['record']['table_id'] for p in plan], [1, 2])
            self.assertTrue(all(p['status'] == 'PLANNED_ONLY' for p in plan))
            self.assertTrue(all(p['record']['hand_verified'] is False for p in plan))

    def test_no_overwrite_mp4(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / 'review_table1_0001.mp4').touch()
            with self.assertRaises(FileExistsError):
                plan_review_exports(handoff(), d)

    def test_no_overwrite_sidecar(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / 'review_table1_0001.json').touch()
            with self.assertRaises(FileExistsError):
                plan_review_exports(handoff(), d)

    def test_rejects_unsafe_promotion(self):
        h = handoff()
        h['windows'][0]['export_approved'] = True
        with self.assertRaises(ValueError):
            plan_review_exports(h, '/tmp')

    def test_rejects_bad_bounds(self):
        h = handoff()
        h['windows'][0]['end_pts'] = 21
        with self.assertRaises(ValueError):
            plan_review_exports(h, '/tmp')

    def test_empty_queue(self):
        h = handoff()
        h['windows'] = []
        self.assertEqual(plan_review_exports(h, '/tmp'), [])

if __name__ == '__main__':
    unittest.main()
