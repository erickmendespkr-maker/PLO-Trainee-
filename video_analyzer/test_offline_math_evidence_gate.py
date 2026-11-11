"""Synthetic evidence gate tests; no recorded hands or poker-site integrations."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from offline_conditional_call_sensitivity import ASSUMPTIONS
import offline_math_evidence_gate as gate

class EvidenceGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.annotation={'schema_version':1,'status':'human_annotation_template_not_approved',
            'source_video_sha256':'a'*64,'hands_reconstructed':False,
            'ready_for_equity_or_ev':False,'annotations':[{
                'event_index':0,'table_id':1,'review_status':'reviewed_complete',
                'hand_id':'synthetic_1','hand_start_seconds':10,'hand_end_seconds':20,
                'variant':'PLO5','hero_cards':['Ac','Kd','Qh','Js','Tc'],
                'board_cards':['2c','3d','4h'],'hero_action':'call',
                'pot_before_action_bb':150,'to_call_bb':50,'review_note':'synthetic only'}]}
        self.scenario={'schema_version':1,
            'source_type':'manually_authored_hypothetical_not_video_verified',
            'scenario_id':'synthetic_1','pot_before_call_bb':150,'call_cost_bb':50,
            'assumptions':copy.deepcopy(ASSUMPTIONS),
            'ranges':[{'range_id':name,'equity':q,'equity_ci95':[q-.01,q+.01],
                'equity_method':'external_independent_monte_carlo_hypothesis',
                'iterations':10000,'seed':7} for name,q in [('wide',.3),('tight',.2)]]}
        self.a=self.root/'annotation.json'
        self.s=self.root/'scenario.json'
        self.write()
    def write(self):
        self.a.write_text(json.dumps(self.annotation),'utf-8')
        self.s.write_text(json.dumps(self.scenario),'utf-8')
    def run_gate(self):
        self.write()
        return gate.run(self.a,self.s,self.root/'result.json')
    def test_synthetic_binding_never_promotes_evidence(self):
        r=self.run_gate()
        self.assertTrue(r['pot_call_values_match'])
        self.assertFalse(r['ready_for_strategic_verdict'])
        self.assertFalse(r['equity_ranges_observed_from_video'])
        self.assertFalse(r['source_hand_reconstruction_verified'])
        self.assertEqual(r['annotation_sha256'],gate.sha(self.a))
        self.assertEqual(r['scenario_sha256'],gate.sha(self.s))
        self.assertEqual(r['conditional_ev_result']['range_results'][0]['ev_call_bb'],10)
        self.assertEqual(json.loads((self.root/'result.json').read_text()),r)
    def test_pot_mismatch(self):
        self.scenario['pot_before_call_bb']=151
        with self.assertRaises(ValueError):self.run_gate()
    def test_call_mismatch(self):
        self.scenario['call_cost_bb']=51
        with self.assertRaises(ValueError):self.run_gate()
    def test_unreviewed(self):
        self.annotation['annotations'][0]['review_status']='pending'
        with self.assertRaises(ValueError):self.run_gate()
    def test_two_calls_ambiguous(self):
        self.annotation['annotations'].append(copy.deepcopy(self.annotation['annotations'][0]))
        with self.assertRaises(ValueError):self.run_gate()
    def test_unsupported_action(self):
        self.annotation['annotations'][0]['hero_action']='raise'
        with self.assertRaises(ValueError):self.run_gate()
    def test_duplicate_cards(self):
        self.annotation['annotations'][0]['board_cards'][0]='Ac'
        with self.assertRaises(ValueError):self.run_gate()
    def test_wrong_variant_card_count(self):
        self.annotation['annotations'][0]['variant']='PLO6'
        with self.assertRaises(ValueError):self.run_gate()
    def test_bad_table(self):
        self.annotation['annotations'][0]['table_id']=5
        with self.assertRaises(ValueError):self.run_gate()
    def test_bad_interval(self):
        self.annotation['annotations'][0]['hand_end_seconds']=9
        with self.assertRaises(ValueError):self.run_gate()
    def test_claimed_verification_rejected(self):
        self.annotation['hands_reconstructed']=True
        with self.assertRaises(ValueError):self.run_gate()
    def test_unsupported_scenario_assumption(self):
        self.scenario['assumptions']['no_rake']=False
        with self.assertRaises(ValueError):self.run_gate()
    def test_boolean_money_rejected(self):
        self.annotation['annotations'][0]['pot_before_action_bb']=True
        with self.assertRaises(ValueError):self.run_gate()
    def test_overwrite_rejected(self):
        self.run_gate()
        with self.assertRaises(ValueError):self.run_gate()
    def test_duplicate_json_key_rejected(self):
        self.a.write_text('{"schema_version":1,"schema_version":1}','utf-8')
        with self.assertRaises(ValueError):gate.read(self.a)
    def test_nan_rejected(self):
        self.a.write_text('{"x":NaN}','utf-8')
        with self.assertRaises(ValueError):gate.read(self.a)
    def test_no_actual_video_required(self):
        self.assertIn('not_independently_verified',self.run_gate()['status'])

if __name__=='__main__':
    unittest.main(verbosity=2)
