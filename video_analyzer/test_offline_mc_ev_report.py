"""Regression tests for offline MC EV provenance."""
import copy
import unittest
from offline_mc_ev_report import build_mc_ev_report

BASE = dict(video_sha256='a'*64, hand_id='table1-001', reviewed=False,
            variant='PLO5', pot_before_call=100, call_cost=50,
            scenarios={'tight': {'seed': 42, 'shares': [0, 1, 0.5, 1],
                                 'range_description': 'synthetic tight range'}})

class TestReport(unittest.TestCase):
    def make(self, **updates):
        x = copy.deepcopy(BASE)
        x.update(updates)
        return build_mc_ev_report(**x)

    def test_unreviewed(self):
        r = self.make()
        self.assertEqual(r['evidence_status'], 'pending_review')
        self.assertFalse(r['strategic_verdict_allowed'])
        self.assertFalse(r['equity_engine_executed'])

    def test_reviewed_still_not_gto(self):
        r = self.make(reviewed=True)
        self.assertEqual(r['evidence_status'], 'reviewed')
        self.assertFalse(r['gto_solution'])

    def test_deterministic_digest(self):
        a = self.make()
        self.assertEqual(a, self.make())
        self.assertEqual(len(a['sampling_provenance']['tight']['samples_sha256']), 64)

    def test_sample_change_digest(self):
        s = copy.deepcopy(BASE['scenarios'])
        s['tight']['shares'][0] = 1
        self.assertNotEqual(self.make()['sampling_provenance']['tight']['samples_sha256'],
                            self.make(scenarios=s)['sampling_provenance']['tight']['samples_sha256'])

    def test_multiple_scenarios(self):
        s = copy.deepcopy(BASE['scenarios'])
        s['loose'] = dict(seed=1, shares=[0, 0], range_description='loose')
        self.assertEqual(len(self.make(scenarios=s)['calculation']['scenarios']), 2)

    def test_bad_hash(self):
        with self.assertRaises(ValueError):
            self.make(video_sha256='X'*64)

    def test_bad_variant(self):
        with self.assertRaises(ValueError):
            self.make(variant='PLO4')

    def test_bad_reviewed(self):
        with self.assertRaises(ValueError):
            self.make(reviewed=1)

    def test_bad_seed(self):
        s = copy.deepcopy(BASE['scenarios'])
        s['tight']['seed'] = True
        with self.assertRaises(ValueError):
            self.make(scenarios=s)

    def test_bad_range(self):
        s = copy.deepcopy(BASE['scenarios'])
        s['tight']['range_description'] = ''
        with self.assertRaises(ValueError):
            self.make(scenarios=s)

    def test_bad_shares(self):
        s = copy.deepcopy(BASE['scenarios'])
        s['tight']['shares'] = [float('nan')]
        with self.assertRaises(ValueError):
            self.make(scenarios=s)

    def test_no_future_claim(self):
        self.assertTrue(any('no future betting' in a for a in self.make()['calculation']['assumptions']))

if __name__ == '__main__':
    unittest.main()
