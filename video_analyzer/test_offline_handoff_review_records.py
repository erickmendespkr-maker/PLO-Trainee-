import copy
import unittest
from offline_handoff_review_records import review_records_from_handoff, ReviewRecordError

BASE = {'type':'provisional_clip_export_handoff','schema_version':1,'source_duration_seconds':10.0,'human_review_required':True,'gto_solution':False,'windows':[{'table_id':1,'start_pts':0.0,'end_pts':5.0,'candidate_ids':['a'],'hand_boundary_verified':False,'human_review_required':True,'export_approved':False,'gto_solution':False,'strategic_conclusion':None}]}

class TestReviewRecords(unittest.TestCase):
    def test_valid(self):
        record=review_records_from_handoff(BASE)[0]
        self.assertFalse(record['hand_verified'])
        self.assertEqual(record['candidate_ids'], ['a'])
    def test_empty(self):
        data=copy.deepcopy(BASE);data['windows']=[]
        self.assertEqual(review_records_from_handoff(data),[])
    def test_invalid_flags(self):
        for field, value in [('hand_boundary_verified',True),('export_approved',True),('strategic_conclusion','blunder'),('gto_solution',True)]:
            with self.subTest(field=field):
                data=copy.deepcopy(BASE);data['windows'][0][field]=value
                with self.assertRaises(ReviewRecordError):review_records_from_handoff(data)
    def test_invalid_bounds(self):
        for start,end in [(-1,3),(2,2),(0,11),(float('nan'),3)]:
            with self.subTest(start=start,end=end):
                data=copy.deepcopy(BASE);data['windows'][0].update(start_pts=start,end_pts=end)
                with self.assertRaises(ReviewRecordError):review_records_from_handoff(data)
    def test_duplicate_ids(self):
        data=copy.deepcopy(BASE);data['windows'][0]['candidate_ids']=['a','a']
        with self.assertRaises(ReviewRecordError):review_records_from_handoff(data)
    def test_bool_table(self):
        data=copy.deepcopy(BASE);data['windows'][0]['table_id']=True
        with self.assertRaises(ReviewRecordError):review_records_from_handoff(data)
    def test_schema(self):
        data=copy.deepcopy(BASE);data['schema_version']=2
        with self.assertRaises(ReviewRecordError):review_records_from_handoff(data)

if __name__=='__main__':unittest.main()
