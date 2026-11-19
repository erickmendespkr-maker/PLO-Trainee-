import unittest
from video_analyzer.offline_equity_ev_confidence import enrich

def sample(q=.28,n=10000,method='MONTE_CARLO'):
    return {'schema_version':1,'equity':q,'trials_or_runouts':n,'method':method,
      'conditional_call_ev':{'call_ev_bb':q*120-30,'is_gto':False},
      'decision_status':'REVIEW_REQUIRED','video_evidence_status':'NOT_VERIFIED'}

class TestConfidence(unittest.TestCase):
    def test_bounds(self):
        r=enrich(sample(),90,30)
        self.assertLess(r['equity_ci95'][0],.28)
        self.assertGreater(r['equity_ci95'][1],.28)
    def test_exact(self):
        self.assertEqual(enrich(sample(method='EXACT'),90,30)['equity_ci95'],[.28,.28])
    def test_more_samples(self):
        a=enrich(sample(n=1000),90,30)['equity_ci95']
        b=enrich(sample(n=100000),90,30)['equity_ci95']
        self.assertGreater(a[1]-a[0],b[1]-b[0])
    def test_no_mutation(self):
        s=sample();enrich(s,90,30);self.assertNotIn('equity_ci95',s)
    def test_review_gate(self):
        s=sample();s['decision_status']='VERIFIED'
        with self.assertRaises(ValueError):enrich(s,90,30)
    def test_ev_gate(self):
        s=sample();s['conditional_call_ev']['call_ev_bb']=999
        with self.assertRaises(ValueError):enrich(s,90,30)
    def test_bad_samples(self):
        with self.assertRaises(ValueError):enrich(sample(n=0),90,30)
    def test_bad_equity(self):
        with self.assertRaises(ValueError):enrich(sample(q=float('nan')),90,30)
    def test_bad_confidence(self):
        with self.assertRaises(ValueError):enrich(sample(),90,30,confidence=1)
    def test_non95(self):
        self.assertIsNone(enrich(sample(),90,30,confidence=.9)['equity_ci95'])
if __name__=='__main__':unittest.main()
