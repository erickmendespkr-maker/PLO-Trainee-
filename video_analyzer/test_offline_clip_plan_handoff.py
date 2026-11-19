import unittest
from video_analyzer.offline_clip_plan_handoff import build_export_requests
SHA='a'*64
def plan():
    return {'schema_version':1,'source_video_sha256':SHA,'analysis_verified':False,
        'clip_plans':[{'hand_id':'abc','table_id':2,'clip_start_seconds':1,'clip_end_seconds':8,
            'crop_xywh':[0,0,160,120],'boundaries_verified':True,
            'strategy_verified':False,'analysis_label':'INSUFFICIENT_DATA'}]}
class TestHandoff(unittest.TestCase):
    def test_request(self):
        r=build_export_requests(plan(),SHA)
        self.assertEqual(r['export_requests'][0]['crop']['width'],160)
        self.assertTrue(r['export_requests'][0]['reviewer_confirmed_offline'])
        self.assertFalse(r['analysis_verified'])
    def test_sha(self):
        with self.assertRaises(ValueError): build_export_requests(plan(),'b'*64)
    def test_unreviewed(self):
        p=plan();p['clip_plans'][0]['boundaries_verified']=False
        with self.assertRaises(ValueError): build_export_requests(p,SHA)
    def test_promoted(self):
        p=plan();p['clip_plans'][0]['strategy_verified']=True
        with self.assertRaises(ValueError): build_export_requests(p,SHA)
    def test_odd_crop(self):
        p=plan();p['clip_plans'][0]['crop_xywh'][0]=1
        with self.assertRaises(ValueError): build_export_requests(p,SHA)
    def test_duplicate(self):
        p=plan();p['clip_plans'].append(dict(p['clip_plans'][0]))
        with self.assertRaises(ValueError): build_export_requests(p,SHA)
if __name__=='__main__': unittest.main()
