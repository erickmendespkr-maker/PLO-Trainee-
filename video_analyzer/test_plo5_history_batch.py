import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from plo5_history_batch import batch, load

EXAMPLES=Path(__file__).resolve().parents[1]/'examples'

class HistoryBatchTests(unittest.TestCase):
    def test_streets_and_prefix_metrics(self):
        r=batch([EXAMPLES/'history_complete.txt'],['flop','river'])
        self.assertEqual(r['consistent_hands'],2);self.assertEqual(r['selection']['evaluated'],2)
        a,b=r['metrics'];self.assertEqual(a['board'],['2c','3d','4h']);self.assertAlmostEqual(a['pot_odds_gross'],1/3)
        self.assertEqual(b['board'],['2c','3d','4h','5s','6s']);self.assertIsNone(b['pot_odds_gross']);self.assertFalse(r['selection']['print_requests'])
    def test_duplicates_and_conflicts(self):
        p=EXAMPLES/'history_complete.txt';r=batch([p,p]);self.assertEqual(r['consistent_hands'],2);self.assertEqual(r['intake']['duplicates'],2)
        r=batch([p,EXAMPLES/'history_strategy.txt']);self.assertEqual(r['consistent_hands'],1);self.assertEqual(r['intake']['conflicts'],1)
        with tempfile.TemporaryDirectory() as t:
            x=Path(t)/'conflict.txt';x.write_text(p.read_text()+'\n'+(EXAMPLES/'history_strategy.txt').read_text());self.assertEqual(batch([x])['consistent_hands'],1)
    def test_unsupported_format_and_bad_record(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'x.txt';p.write_text('unknown format');r=batch([p]);self.assertEqual(r['consistent_hands'],0);self.assertEqual(r['intake']['rejected'][0]['reason'],'UNSUPPORTED_FORMAT')
            p.write_text((EXAMPLES/'history_strategy.txt').read_text().replace('Total pot $8','Total pot $9'));r=batch([p]);self.assertEqual(r['consistent_hands'],0);self.assertTrue(r['intake']['rejected'])
    def test_native_integration(self):
        config=json.loads((EXAMPLES/'history_strategy.json').read_text())['decisions'][0];config={k:v for k,v in config.items() if k not in ('hand_id','event_index')};config['iterations']=1
        with tempfile.TemporaryDirectory() as t:
            r=batch([EXAMPLES/'history_strategy.txt'],['river'],configs={'1':config},cache=Path(t)/'cache.sqlite',cfr_executable=os.environ.get('PLO5_MULTIWAY_EXE'))
            self.assertEqual(len(r['experimental_estimates']),1);e=r['experimental_estimates'][0];self.assertEqual(e['status'],'EXPERIMENTAL_MODEL_ONLY');self.assertEqual(e['estimate']['state']['board'],r['metrics'][0]['board']);self.assertFalse(r['selection']['errors']);self.assertEqual(len(r['selection']['unresolved']),1)
            with patch('plo5_history_batch.evaluate_model') as f:
                batch([EXAMPLES/'history_strategy.txt'],['preflop'],configs={'1':config},cache=Path(t)/'cache.sqlite');f.assert_not_called()
    def test_future_cards_and_outcomes_not_used(self):
        p=EXAMPLES/'history_strategy.txt'
        with tempfile.TemporaryDirectory() as t:
            x=Path(t)/'other.txt';x.write_text(p.read_text().replace('[6s]','[7s]'))
            a=batch([p],['flop']);b=batch([x],['flop']);self.assertEqual(b['consistent_hands'],1)
            def context(r):return [{k:v for k,v in m.items() if not k.endswith('sha256')} for m in r['metrics']]
            self.assertEqual(context(a),context(b));self.assertEqual(a['selection'],b['selection'])

if __name__=='__main__':unittest.main()
