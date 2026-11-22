import unittest
from offline_decision_report import decision_report
SHA='a'*64
READY={'status':'READY_FOR_CONDITIONAL_ANALYSIS','missing_fields':[],'invalid_fields':[],'unverified_fields':[]}
class ReportTests(unittest.TestCase):
    def build(self,a=None,**kwargs):
        return decision_report(a if a is not None else {'status':'INSUFFICIENT_DATA','evidence':READY},video_sha256=SHA,clip_start_s=1,clip_end_s=3,**kwargs)
    def test_insufficient_never_promotes_ev(self):
        r=self.build({'status':'INSUFFICIENT_DATA','evidence':READY,'conditional_ev':{'ev_low_chips':100}})
        self.assertIsNone(r['conditional_ev']); self.assertIsNone(r['strategic_conclusion'])
    def test_unreviewed_never_promotes_ev(self):
        r=self.build({'status':'CONDITIONAL_EV_ONLY','evidence':{'status':'INSUFFICIENT_DATA'},'scenario_id':'x','conditional_ev':{'ev_low_chips':1,'ev_high_chips':2}})
        self.assertEqual(r['status'],'INSUFFICIENT_DATA')
    def test_conditional_bounds(self):
        r=self.build({'status':'CONDITIONAL_EV_ONLY','evidence':READY,'scenario_id':'tight','conditional_ev':{'ev_low_chips':-5,'ev_high_chips':25}})
        self.assertEqual(r['conditional_ev']['ev_high_chips'],25)
        self.assertFalse(r['clip']['reviewed'])
    def test_invalid_bounds(self):
        with self.assertRaises(ValueError): self.build({'status':'CONDITIONAL_EV_ONLY','evidence':READY,'scenario_id':'x','conditional_ev':{'ev_low_chips':2,'ev_high_chips':1}})
    def test_missing_scenario(self):
        with self.assertRaises(ValueError): self.build({'status':'CONDITIONAL_EV_ONLY','evidence':READY,'conditional_ev':{'ev_low_chips':1,'ev_high_chips':2}})
    def test_invalid_hash(self):
        with self.assertRaises(ValueError): decision_report({'evidence':READY},video_sha256='X'*64,clip_start_s=1,clip_end_s=2)
    def test_invalid_time(self):
        with self.assertRaises(ValueError): decision_report({'evidence':READY},video_sha256=SHA,clip_start_s=2,clip_end_s=2)
    def test_missing_evidence(self):
        with self.assertRaises(ValueError): self.build({'status':'INSUFFICIENT_DATA'})
if __name__=='__main__': unittest.main()
