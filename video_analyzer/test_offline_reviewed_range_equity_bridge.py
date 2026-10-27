"""Synthetic tests: no video observations or live poker inputs."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from offline_reviewed_range_equity_bridge import analyze, export


def fixture(variant="PLO5", board=None):
    hero=["Ac","Kd","Qh","Js","Tc"] + (["9d"] if variant=="PLO6" else [])
    villain=["2d","3h","4s","5c","6d"] + (["7h"] if variant=="PLO6" else [])
    return {
        "schema_version":1,
        "review_gate":{"status":"synthetic_fixture","reviewer_label":"unit-test"},
        "reviewed_hand":{
            "schema_version":1,"variant":variant,"table_id":1,
            "hand_label":"synthetic-hand","source_recording_sha256_claim":"a"*64,
            "annotation_source":"synthetic","hero_cards":hero,
            "board_cards":board if board is not None else ["8c","8d","8h","9s","2c"],
            "opponent_range":{"label":"explicit_synthetic_combo","opponents":1,
                              "assumptions":["One hypothetical hand; not video-derived"]},
            "equity_estimate":None,
            "decision":{"action":"call","pot_before_call":100,"call_cost":40,
                        "remaining_stack":100,"expected_rake":0,
                        "no_future_betting":True,"no_side_pots":True},
            "unresolved_fields":[]},
        "weighted_range":[{"cards":villain,"weight":1}],
        "monte_carlo":{"trials":100,"seed":42}}


class BridgeTests(unittest.TestCase):
    def test_recomputes_and_reproducible(self):
        a=analyze(fixture());b=analyze(fixture())
        self.assertEqual(a,b)
        self.assertTrue(a['monte_carlo_recomputed'])
        self.assertEqual(a['wins']+a['ties']+a['losses'],100)
        self.assertAlmostEqual(a['ev_call_chips'],a['equity']*140-40)
        self.assertFalse(a['video_evidence_verified'])
        self.assertFalse(a['strategic_error_proven'])
        self.assertFalse(a['automatic_clip_selection_authorized'])
    def test_plo6(self):
        self.assertEqual(analyze(fixture('PLO6'))['variant'],'PLO6')
    def test_flop_sampling(self):
        d=fixture(board=['8c','8d','8h'])
        self.assertEqual(analyze(d)['wins']+analyze(d)['ties']+analyze(d)['losses'],100)
    def test_block_unresolved(self):
        d=fixture();d['reviewed_hand']['unresolved_fields']=['unreadable pot']
        r=analyze(d)
        self.assertFalse(r['monte_carlo_recomputed']);self.assertIn('unresolved_annotations',r['blocked_reasons'])
    def test_block_future_betting(self):
        d=fixture();d['reviewed_hand']['decision']['no_future_betting']=False
        self.assertFalse(analyze(d)['monte_carlo_recomputed'])
    def test_block_multiway(self):
        d=fixture();d['reviewed_hand']['opponent_range']['opponents']=2
        self.assertFalse(analyze(d)['monte_carlo_recomputed'])
    def test_block_raise(self):
        d=fixture();d['reviewed_hand']['decision']['action']='raise'
        self.assertFalse(analyze(d)['monte_carlo_recomputed'])
    def test_gate_mismatch(self):
        d=fixture();d['review_gate']['status']='human_confirmed_claim'
        self.assertIn('human_gate_annotation_mismatch',analyze(d)['blocked_reasons'])
    def test_no_external_equity(self):
        d=fixture();d['reviewed_hand']['equity_estimate']={'method':'external'}
        with self.assertRaises(ValueError):analyze(d)
    def test_range_collision(self):
        d=fixture();d['weighted_range'][0]['cards'][0]='Ac'
        with self.assertRaises(ValueError):analyze(d)
    def test_range_duplicate(self):
        d=fixture();d['weighted_range'].append(copy.deepcopy(d['weighted_range'][0]))
        with self.assertRaises(ValueError):analyze(d)
    def test_range_duplicate_permuted(self):
        d=fixture();entry=copy.deepcopy(d['weighted_range'][0]);entry['cards'].reverse();d['weighted_range'].append(entry)
        with self.assertRaises(ValueError):analyze(d)
    def test_range_all_zero(self):
        d=fixture();d['weighted_range'][0]['weight']=0
        with self.assertRaises(ValueError):analyze(d)
    def test_invalid_weight(self):
        for weight in (True,-1,float('nan'),float('inf'),1e13):
            d=fixture();d['weighted_range'][0]['weight']=weight
            with self.subTest(weight=weight),self.assertRaises(ValueError):analyze(d)
    def test_bad_trial_counts(self):
        for trials in (0,99,50001,True,1.5):
            d=fixture();d['monte_carlo']['trials']=trials
            with self.subTest(trials=trials),self.assertRaises(ValueError):analyze(d)
    def test_bad_seed(self):
        for seed in (-1,True,2**64):
            d=fixture();d['monte_carlo']['seed']=seed
            with self.subTest(seed=seed),self.assertRaises(ValueError):analyze(d)
    def test_unsafe_extra_key(self):
        d=fixture();d['auto_export_clips']=True
        with self.assertRaises(ValueError):analyze(d)
    def test_export_no_overwrite(self):
        with tempfile.TemporaryDirectory() as t:
            src=Path(t)/'in.json';dst=Path(t)/'out.json'
            src.write_text(json.dumps(fixture()))
            report=export(src,dst)
            self.assertEqual(json.loads(dst.read_text())['equity'],report['equity'])
            with self.assertRaises(ValueError):export(src,dst)
    def test_export_duplicate_keys(self):
        with tempfile.TemporaryDirectory() as t:
            src=Path(t)/'in.json';dst=Path(t)/'out.json'
            src.write_text('{"schema_version":1,"schema_version":1}')
            with self.assertRaises(ValueError):export(src,dst)
    def test_export_symlink(self):
        with tempfile.TemporaryDirectory() as t:
            src=Path(t)/'in.json';link=Path(t)/'link.json';dst=Path(t)/'out.json'
            src.write_text(json.dumps(fixture()));link.symlink_to(src)
            with self.assertRaises(ValueError):export(link,dst)
    def test_interval_contains_estimate(self):
        r=analyze(fixture());lo,hi=r['equity_ci95_hoeffding']
        self.assertLessEqual(lo,r['equity']);self.assertGreaterEqual(hi,r['equity'])
        self.assertLessEqual(r['ev_call_interval_chips'][0],r['ev_call_chips'])
        self.assertGreaterEqual(r['ev_call_interval_chips'][1],r['ev_call_chips'])
    def test_human_gate_claim_not_video_verification(self):
        d=fixture();d['review_gate']['status']='human_confirmed_claim'
        d['reviewed_hand']['annotation_source']='human_annotation'
        r=analyze(d)
        self.assertTrue(r['monte_carlo_recomputed'])
        self.assertFalse(r['video_evidence_verified'])

    def test_two_weighted_combos_reproducible(self):
        d=fixture(board=['8c','8d','8h'])
        d['weighted_range'].append({'cards':['2s','3c','4d','5h','6s'],'weight':3})
        d['monte_carlo']['seed']=17
        a=analyze(d);b=analyze(d)
        self.assertEqual(a,b)
        self.assertEqual(a['range_combos_supplied'],2)
        self.assertEqual(a['wins']+a['ties']+a['losses'],100)
        self.assertLessEqual(a['equity_ci95_hoeffding'][0],a['equity'])

    def test_rake_affects_ev(self):
        d=fixture();r0=analyze(d);d['reviewed_hand']['decision']['expected_rake']=3
        self.assertAlmostEqual(analyze(d)['ev_call_chips'],r0['ev_call_chips']-3)


if __name__=='__main__':unittest.main()
