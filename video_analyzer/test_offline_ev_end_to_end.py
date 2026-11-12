"""Synthetic integration: assumed equity -> conditional EV -> review binding.

No real video or GTO conclusion is asserted.
"""
import copy
import unittest
from offline_ev_sensitivity import evaluate_call_scenarios
from offline_ev_binding_adapter import adapt_sensitivity
from offline_review_ev_binding import bind

def artifacts():
    raw = evaluate_call_scenarios(150, 50, [
        {'range_id':'tight','equity':.20,'equity_ci':[.18,.22],'iterations':10000,'seed':1},
        {'range_id':'loose','equity':.30,'equity_ci':[.28,.32],'iterations':10000,'seed':2}])
    ev = adapt_sensitivity(raw, 'synthetic_ranges_1')
    review = dict(schema_version=1,hand_id='synthetic_h1',table_id=1,
        source_video_sha256='a'*64,start_seconds=10.,end_seconds=25.,
        action='call',pot_bb=150.,call_bb=50.)
    gate = dict(schema_version=1,hand_id='synthetic_h1',table_id=1,
        source_video_sha256='a'*64,analysis_status='READY_FOR_CONDITIONAL_MODEL',
        missing_or_unconfirmed=[],source_hand_reconstruction_verified=False,
        strategic_error_established=False,gto_solution=False)
    return raw,ev,review,gate

class SyntheticPipelineTests(unittest.TestCase):
    def test_pipeline_conditional_only(self):
        raw,ev,review,gate=artifacts()
        result=bind(review,gate,ev)
        self.assertEqual(result['analysis_status'],'CONDITIONAL_MODEL_REVIEW_ONLY')
        self.assertEqual(result['range_count'],2)
        self.assertTrue(result['range_sensitive'])
        self.assertFalse(result['automatic_clip_selection_authorized'])
        self.assertFalse(result['strategic_error_established'])
        self.assertFalse(result['gto_solution'])
        self.assertAlmostEqual(ev['range_results'][0]['ev_call_bb'],-10)
        self.assertAlmostEqual(ev['range_results'][1]['ev_call_bb'],10)
        self.assertEqual(raw['scenarios'][0]['seed'],1)

    def test_missing_evidence_stays_insufficient(self):
        _,ev,review,gate=artifacts()
        gate['analysis_status']='INSUFFICIENT_DATA'
        gate['missing_or_unconfirmed']=['hero_cards']
        result=bind(review,gate,ev)
        self.assertEqual(result['analysis_status'],'INSUFFICIENT_DATA')
        self.assertFalse(result['automatic_clip_selection_authorized'])

    def test_mismatched_recording_rejected(self):
        _,ev,review,gate=artifacts()
        gate['source_video_sha256']='b'*64
        with self.assertRaises(ValueError): bind(review,gate,ev)

    def test_ev_tampering_rejected(self):
        _,ev,review,gate=artifacts()
        ev['range_results'][0]['ev_call_bb']=99
        with self.assertRaises(ValueError): bind(review,gate,ev)

    def test_input_equity_interval_rejected(self):
        with self.assertRaises(ValueError):
            evaluate_call_scenarios(150,50,[
                {'range_id':'a','equity':.3,'equity_ci':[.4,.5],'iterations':10,'seed':1},
                {'range_id':'b','equity':.2,'equity_ci':[.1,.3],'iterations':10,'seed':2}])

    def test_no_implicit_video_verification(self):
        _,ev,review,gate=artifacts()
        gate['source_hand_reconstruction_verified']=True
        with self.assertRaises(ValueError): bind(review,gate,ev)

    def test_deterministic_binding_hashes(self):
        _,ev,review,gate=artifacts()
        a=bind(review,gate,ev)
        b=bind(copy.deepcopy(review),copy.deepcopy(gate),copy.deepcopy(ev))
        self.assertEqual(a,b)

if __name__=='__main__':
    unittest.main()
