"""Opt-in native parity tests; compile the official CLI, set PLO5_CFR_EXE."""
import os
import random
import subprocess
import unittest
from pathlib import Path
from test_plo5_post_gto_river import context, polar, oracle, NUT, BLUFF, CATCH, BOARD
from plo5_post_gto_river import solve

EXE = os.environ.get('PLO5_CFR_EXE')


@unittest.skipUnless(EXE, 'PLO5_CFR_EXE not provided')
class NativeRiverTests(unittest.TestCase):
    def parity(self, c, **kwargs):
        a = solve(c, **kwargs)
        b = solve(c, cfr_executable=EXE, **kwargs)
        self.assertEqual(b['backend'], 'native')
        self.assertEqual(a['backend'], 'python')
        for k in ('variant', 'context_key', 'iterations', 'nodes', 'legal_pairs'):
            self.assertEqual(a[k], b[k], k)
        for k in ('value_bb', 'best_response_lower_bb', 'best_response_upper_bb',
                  'nash_gap_bb', 'gap_fraction_of_pot'):
            self.assertAlmostEqual(a[k], b[k], delta=1e-8, msg=k)
        self.assertEqual(len(a['policy']), len(b['policy']))
        for x, y in zip(a['policy'], b['policy']):
            for k in ('node', 'position', 'holding'):
                self.assertEqual(x[k], y[k])
            self.assertAlmostEqual(x['opponent_reach_mass'], y['opponent_reach_mass'], delta=1e-8)
            self.assertEqual(len(x['actions']), len(y['actions']))
            for u, v in zip(x['actions'], y['actions']):
                self.assertEqual((u['action'], u['amount']), (v['action'], v['amount']))
                self.assertAlmostEqual(u['frequency'], v['frequency'], delta=1e-8)
                if u['ev_bb'] is None:
                    self.assertIsNone(v['ev_bb'])
                else:
                    self.assertAlmostEqual(u['ev_bb'], v['ev_bb'], delta=1e-8)
        return b

    def test_polar_normal_form(self):
        for n in (1, 50, 100, 500, 1000, 5000):
            with self.subTest(iterations=n):
                r = self.parity(polar(), iterations=n, pot_bps=())
                for x, y in zip((r['value_bb'], r['best_response_lower_bb'],
                                 r['best_response_upper_bb']), oracle(r)):
                    self.assertAlmostEqual(x, y, delta=1e-9)

    def test_known_outcomes_and_blockers(self):
        cases = [context([(NUT, 1)], [(CATCH, 1)]),
                 context([(CATCH, 1)], [(NUT, 1)]),
                 context([(NUT, 3), (BLUFF, 2)], [(CATCH, 7), (NUT, 1)]),
                 context([('As 5s Qh Jd Tc'.split(), 1)],
                         [('Ah 5h Qs Jc Td'.split(), 1)], '2c 3d 4h 9s Kc'.split())]
        for i, c in enumerate(cases):
            with self.subTest(case=i):
                self.parity(c, iterations=300, pot_bps=())

    def test_weighted_random_ranges(self):
        rng = random.Random(27112026)
        deck = [r+s for r in '23456789TJQKA' for s in 'cdhs' if r+s not in BOARD]
        for i in range(8):
            a, b = [[(rng.sample(deck, 5), rng.randrange(1, 30)) for _ in range(4)] for _ in range(2)]
            with self.subTest(case=i):
                self.parity(context(a, b, stacks=(4+i, 5+i), pot=6, bb=2),
                            iterations=100, pot_bps=(5000, 10000))

    def test_deep_and_asymmetric_stacks(self):
        for stacks in ((100, 100), (100, 17), (20, 3), (3, 20)):
            with self.subTest(stacks=stacks):
                self.parity(context([(NUT, 1), (BLUFF, 2)], [(CATCH, 1)],
                                    stacks=stacks, pot=20, bb=2),
                            iterations=100, pot_bps=(5000, 10000))

    def test_reject_invalid_protocol(self):
        bad = ('0 1 1 1\n', '3 1 1 1\n1.1 1\n',
               '3 1 1 1\n1 2\n', '3 1 1 1\n1 0\n0 2 0 0 1 1 0\n',
               '3 1 1 1\n1 0\n0 2 0 0 1 2 0\n-1 0 0 0\n-1 0 0 0\nBOGUS\n')
        for data in bad:
            with self.subTest(data=data):
                r = subprocess.run([str(Path(EXE).resolve())], input=data, text=True,
                                   capture_output=True, timeout=5)
                self.assertNotEqual(r.returncode, 0)
                self.assertFalse(r.stdout)

    def test_missing_executable_fails_closed(self):
        with self.assertRaises(FileNotFoundError):
            solve(polar(), cfr_executable=str(Path(EXE).resolve())+'.missing')


if __name__ == '__main__':
    unittest.main(verbosity=2)
