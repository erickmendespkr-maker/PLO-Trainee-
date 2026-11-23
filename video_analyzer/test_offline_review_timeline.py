import unittest
from offline_review_timeline import audit_review_timeline as audit

class TimelineTests(unittest.TestCase):
    def test_empty(self): self.assertEqual(audit({'hands': []})['status'], 'TIMELINE_PLAUSIBLE')
    def test_sequential(self): self.assertEqual(audit({'hands': [{'table_id': 1, 'start_s': 0, 'end_s': 3}, {'table_id': 1, 'start_s': 3, 'end_s': 6}]})['issues'], [])
    def test_parallel_tables(self): self.assertEqual(audit({'hands': [{'table_id': 1, 'start_s': 0, 'end_s': 3}, {'table_id': 2, 'start_s': 0, 'end_s': 3}]})['issues'], [])
    def test_overlap(self): self.assertEqual(audit({'hands': [{'table_id': 1, 'start_s': 0, 'end_s': 5}, {'table_id': 1, 'start_s': 2, 'end_s': 4}]})['issues'][0]['code'], 'SAME_TABLE_OVERLAP')
    def test_invalid_interval(self): self.assertEqual(audit({'hands': [{'table_id': 1, 'start_s': 4, 'end_s': 4}]})['issues'][0]['code'], 'INVALID_INTERVAL')
    def test_missing_table(self): self.assertEqual(audit({'hands': [{'table_id': None, 'start_s': 0, 'end_s': 3}]})['issues'][0]['code'], 'UNKNOWN_TABLE')
    def test_outside(self): self.assertEqual(audit({'hands': [{'table_id': 1, 'start_s': 0, 'end_s': 6}]}, duration_s=5)['issues'][0]['code'], 'OUTSIDE_VIDEO')
    def test_nan(self): self.assertEqual(audit({'hands': [{'table_id': 1, 'start_s': float('nan'), 'end_s': 3}]})['issues'][0]['code'], 'INVALID_INTERVAL')
    def test_invalid_duration(self):
        with self.assertRaises(ValueError): audit({'hands': []}, duration_s=0)
    def test_invalid_history(self):
        with self.assertRaises(ValueError): audit({})
    def test_boolean_table(self): self.assertEqual(audit({'hands': [{'table_id': True, 'start_s': 0, 'end_s': 1}]})['issues'][0]['code'], 'UNKNOWN_TABLE')
    def test_nested_overlap(self): self.assertEqual(len(audit({'hands': [{'table_id': 1, 'start_s': 0, 'end_s': 10}, {'table_id': 1, 'start_s': 1, 'end_s': 2}, {'table_id': 1, 'start_s': 3, 'end_s': 4}]})['issues']), 2)

if __name__ == '__main__': unittest.main()
