"""Regression tests for the offline reviewed-hand ledger."""
import json
import tempfile
import unittest
from pathlib import Path
try:
    from .offline_review_history import build_review_history, write_review_history
except ImportError:
    from offline_review_history import build_review_history, write_review_history

SHA = 'a' * 64

def sample(variant='PLO5', verified=True):
    hero = ['As','Ks','Qs','Js','Ts'] if variant == 'PLO5' else ['As','Ks','Qs','Js','Ts','9s']
    raw = {'table_id': 'table-1', 'hand_start_s': 2, 'hand_end_s': 14,
           'hero_cards': hero, 'board': ['2c','3d','4h'], 'action': 'call', 'pot': 100, 'amount': 20}
    return {'variant': variant, 'evidence': {k: {'value': v, 'confidence': .99, 'human_verified': verified} for k,v in raw.items()}}

class TestHistory(unittest.TestCase):
    def test_reviewed_plo5(self):
        r=build_review_history(SHA,[sample()])
        self.assertEqual(r['summary']['ready_for_conditional_analysis'],1)
        self.assertIsNone(r['hands'][0]['ev'])
        self.assertFalse(r['equity_or_ev_computed'])
    def test_reviewed_plo6(self):
        self.assertEqual(build_review_history(SHA,[sample('PLO6')])['summary']['ready_for_conditional_analysis'],1)
    def test_unverified(self):
        self.assertEqual(build_review_history(SHA,[sample(verified=False)])['summary']['insufficient_data'],1)
    def test_duplicate_card(self):
        x=sample(); x['evidence']['board']['value']=['As','3d','4h']
        self.assertFalse(build_review_history(SHA,[x])['hands'][0]['conditional_analysis_allowed'])
    def test_bad_interval(self):
        x=sample(); x['evidence']['hand_end_s']['value']=1
        self.assertEqual(build_review_history(SHA,[x])['hands'][0]['status'],'INSUFFICIENT_DATA')
    def test_bad_digest(self):
        with self.assertRaises(ValueError): build_review_history('bad',[sample()])
    def test_bad_variant(self):
        with self.assertRaises(ValueError): build_review_history(SHA,[sample('PLO4')])
    def test_no_hands(self):
        self.assertEqual(build_review_history(SHA,[])['summary']['total'],0)
    def test_write_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'history.json'; r=build_review_history(SHA,[sample()])
            digest=write_review_history(p,r)
            self.assertEqual(json.loads(p.read_text())['summary']['total'],1)
            self.assertEqual(len(digest),64)
            with self.assertRaises(FileExistsError): write_review_history(p,r)
    def test_nan_rejected_from_times(self):
        x=sample(); x['evidence']['hand_start_s']['value']=float('nan')
        r=build_review_history(SHA,[x]); self.assertIsNone(r['hands'][0]['start_s'])
        json.dumps(r,allow_nan=False)

if __name__=='__main__':
    unittest.main()
