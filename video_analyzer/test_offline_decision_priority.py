import unittest
from offline_decision_priority import prioritize_decisions


def decision(hand='h1', bounds=((-5,-2),(-4,-1)), **kw):
    return dict(hand_id=hand, decision_id='d1', review_status='CONDITIONAL_ANALYSIS_PERMITTED', evidence_confidence=.95,
                scenarios=[dict(range_label=f'r{i}', ev_difference_interval=list(b)) for i,b in enumerate(bounds)], **kw)

class DecisionPriorityTests(unittest.TestCase):
    def test_robust_loss(self):
        x=prioritize_decisions([decision()]); self.assertEqual(x['selected_for_review'][0]['conservative_loss_lower_bound'],1)
    def test_positive(self):
        self.assertEqual(prioritize_decisions([decision(bounds=((1,2),))])['candidates'][0]['status'],'MODELLED_GAIN_CANDIDATE')
    def test_sensitive(self):
        self.assertEqual(prioritize_decisions([decision(bounds=((-1,2),))])['candidates'][0]['status'],'RANGE_OR_SAMPLING_SENSITIVE')
    def test_unreviewed(self):
        d=decision(); d['review_status']='INSUFFICIENT_DATA'; self.assertFalse(prioritize_decisions([d])['selected_for_review'])
    def test_low_confidence(self):
        d=decision(); d['evidence_confidence']=.5; self.assertFalse(prioritize_decisions([d])['selected_for_review'])
    def test_sort(self):
        a=decision('a',((-10,-4),)); b=decision('b',((-4,-1),)); self.assertEqual(prioritize_decisions([b,a],max_clips=1)['selected_for_review'][0]['hand_id'],'a')
    def test_duplicate(self):
        with self.assertRaises(ValueError): prioritize_decisions([decision(),decision()])
    def test_nan(self):
        d=decision(); d['scenarios'][0]['ev_difference_interval']=[float('nan'),0]
        with self.assertRaises(ValueError): prioritize_decisions([d])
    def test_missing(self):
        d=decision(); d['scenarios']=[]; self.assertEqual(prioritize_decisions([d])['candidates'][0]['status'],'INSUFFICIENT_DATA')
    def test_no_auto_clip(self):
        self.assertFalse(prioritize_decisions([decision()])['clip_export_authorized'])

if __name__=='__main__': unittest.main()
