import unittest
from offline_table_timeline import build_table_timeline

def obs(t, *ids):
    return {'timestamp_seconds': t, 'tables': [{'table_id': i, 'confidence': .9} for i in ids]}

class TimelineTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(build_table_timeline([])['segments'], [])
    def test_four_to_three_to_one(self):
        r = build_table_timeline([obs(0,1,2,3,4), obs(5,1,2,3), obs(10,2)])
        self.assertEqual([(s['table_id'], s['sample_count']) for s in r['segments']], [(1,2),(2,3),(3,2),(4,1)])
        self.assertFalse(r['hand_boundaries_verified'])
    def test_gap_breaks_segment(self):
        self.assertEqual(len(build_table_timeline([obs(0,1),obs(20,1)])['segments']), 2)
    def test_absence_breaks_segment(self):
        self.assertEqual(len(build_table_timeline([obs(0,1),obs(1),obs(2,1)])['segments']), 2)
    def test_minimum_confidence(self):
        r=build_table_timeline([obs(0,1), {'timestamp_seconds':1,'tables':[{'table_id':1,'confidence':.2}]}])
        self.assertEqual(r['segments'][0]['minimum_confidence'],.2)
    def test_duplicate_table(self):
        with self.assertRaises(ValueError): build_table_timeline([obs(0,1,1)])
    def test_duplicate_timestamp(self):
        with self.assertRaises(ValueError): build_table_timeline([obs(0,1),obs(0,2)])
    def test_invalid_confidence(self):
        with self.assertRaises(ValueError): build_table_timeline([{'timestamp_seconds':0,'tables':[{'table_id':1,'confidence':float('nan')}]}])
    def test_bad_id(self):
        with self.assertRaises(ValueError): build_table_timeline([obs(0,5)])
    def test_bad_gap(self):
        with self.assertRaises(ValueError): build_table_timeline([],max_gap_seconds=0)
    def test_no_hand_claims(self):
        r=build_table_timeline([obs(0,1),obs(1,1)])
        self.assertFalse(r['analysis_verified'])
        self.assertFalse(r['segments'][0]['verified_by_human'])
if __name__ == '__main__':
    unittest.main()
