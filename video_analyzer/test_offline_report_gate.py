import unittest
from video_analyzer.offline_report_gate import build_review_packet
SHA='a'*64
H=dict(table_id=1,start_pts_seconds=10,end_pts_seconds=20,source_video_sha256=SHA,review_status='HUMAN_REVIEWED',hand_boundary_verified=True,cards_verified=True,action_verified=True,variant='PLO5',hero_cards=['Ah','Kd','Qc','Js','Th'],board_cards=['2c','3d','4h'])
R=dict(variant='PLO5',hero=H['hero_cards'],board=H['board_cards'],is_gto=False,decision_status='REVIEW_REQUIRED',video_evidence_status='NOT_VERIFIED',opponents=[[]],equity=.28,conditional_call_ev={'is_gto':False,'call_ev_bb':3.6})
class Tests(unittest.TestCase):
 def test_valid(self):
  x=build_review_packet(H,R,video_sha256=SHA,duration_seconds=30)
  self.assertEqual(x['analysis_status'],'CONDITIONAL_MODEL_REVIEW_REQUIRED')
  self.assertFalse(x['is_definitive_error'])
 def test_multiway(self):
  with self.assertRaises(ValueError):build_review_packet(H,{**R,'opponents':[[],[]]},video_sha256=SHA,duration_seconds=30)
 def test_unreviewed(self):
  with self.assertRaises(ValueError):build_review_packet({**H,'review_status':'PENDING'},R,video_sha256=SHA,duration_seconds=30)
 def test_cards_mismatch(self):
  with self.assertRaises(ValueError):build_review_packet({**H,'hero_cards':[]},R,video_sha256=SHA,duration_seconds=30)
 def test_bad_sha(self):
  with self.assertRaises(ValueError):build_review_packet(H,R,video_sha256='b'*64,duration_seconds=30)
 def test_bad_ev(self):
  with self.assertRaises(ValueError):build_review_packet(H,{**R,'conditional_call_ev':{'is_gto':False,'call_ev_bb':float('nan')}},video_sha256=SHA,duration_seconds=30)
if __name__=='__main__':unittest.main()
