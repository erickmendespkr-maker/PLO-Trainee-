import unittest
from video_analyzer.offline_loss_clip_handoff import build_loss_clip_plan

HASH='a'*64

def queue():
    return {'analysis_verified':False,'is_gto':False,'review_queue':[
        {'hand_id':'h1','table_id':1,'start_seconds':12,'end_seconds':28,'strategy_verified':False,
         'loss_over_30bb':True,'loss_evidence':{'hand_id':'h1','table_id':1,'confirmed_loss_bb':40,'strategy_verified':False}}]}

def review():
    return [{'hand_id':'h1','table_id':1,'boundaries_verified':True,'crop_verified':True,
             'strategy_verified':False,'clip_start_seconds':10,'clip_end_seconds':30,'crop_xywh':[0,0,400,300]}]

class Tests(unittest.TestCase):
    def test_valid(self):
        p=build_loss_clip_plan(queue(),review(),HASH)
        self.assertEqual(p['clip_plans'][0]['analysis_label'],'INSUFFICIENT_DATA')
        self.assertFalse(p['analysis_verified'])
    def test_unverified_boundary(self):
        r=review();r[0]['boundaries_verified']=False
        with self.assertRaises(ValueError):build_loss_clip_plan(queue(),r,HASH)
    def test_unverified_crop(self):
        r=review();r[0]['crop_verified']=False
        with self.assertRaises(ValueError):build_loss_clip_plan(queue(),r,HASH)
    def test_loss_not_confirmed(self):
        q=queue();q['review_queue'][0]['loss_over_30bb']=False
        with self.assertRaises(ValueError):build_loss_clip_plan(q,review(),HASH)
    def test_loss_at_threshold(self):
        q=queue();q['review_queue'][0]['loss_evidence']['confirmed_loss_bb']=30
        with self.assertRaises(ValueError):build_loss_clip_plan(q,review(),HASH)
    def test_incomplete_interval(self):
        r=review();r[0]['clip_start_seconds']=15
        with self.assertRaises(ValueError):build_loss_clip_plan(queue(),r,HASH)
    def test_odd_crop(self):
        r=review();r[0]['crop_xywh']=[1,0,400,300]
        with self.assertRaises(ValueError):build_loss_clip_plan(queue(),r,HASH)
    def test_duplicate(self):
        with self.assertRaises(ValueError):build_loss_clip_plan(queue(),review()*2,HASH)
    def test_orphan(self):
        r=review();r[0]['hand_id']='unknown'
        with self.assertRaises(ValueError):build_loss_clip_plan(queue(),r,HASH)
    def test_bad_sha(self):
        with self.assertRaises(ValueError):build_loss_clip_plan(queue(),review(),'bad')
    def test_strategy_promotion(self):
        r=review();r[0]['strategy_verified']=True
        with self.assertRaises(ValueError):build_loss_clip_plan(queue(),r,HASH)
    def test_custom_threshold(self):
        with self.assertRaises(ValueError):build_loss_clip_plan(queue(),review(),HASH,threshold_bb=40)

if __name__=='__main__': unittest.main()
