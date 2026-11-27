"""Independent normal-form oracle for a nine-node PLO5 river subgame."""
import itertools
import math
import time
import unittest
from plo5_post_gto_river import solve
from plo5_post_gto_tree import start, step, bounds

NUT = 'As Ks 4c 5d 6h'.split()
BLUFF = '7c 8d 9h 4d 5h'.split()
CATCH = '9s 8s 6c 7d 2h'.split()
BOARD = 'Qs Js Ts 2d 3c'.split()


def context(a, b, board=BOARD, stacks=(2, 2), pot=2, bb=1):
    def rows(entries):
        return [dict(cards=h, weight=w) for h, w in entries]
    return dict(variant=5, board=list(board), seats=['BB', 'BTN'], actor='BB',
                pot=pot, bb=bb, stacks=dict(zip(['BB', 'BTN'], stacks)),
                ranges={'BB': rows(a), 'BTN': rows(b)}, rake_bps=0, rake_cap=0,
                tree_version='test', continuation_version='terminal')


def polar():
    return context([(NUT, 1), (BLUFF, 2)], [(CATCH, 1)])


def oracle(result):
    # Fixed topology, pot and stack 2, no raises. Payoffs derive from cash flows,
    # not the production tree, rank evaluator, CFR updates or BR implementation.
    p = {(r['node'], tuple(r['holding'])): r for r in result['policy']}
    hands = [tuple(sorted(h)) for h in (NUT, BLUFF)]
    v = tuple(sorted(CATCH))
    keys0 = [(n, h) for n in (0, 3) for h in hands]
    keys1 = [(n, v) for n in (1, 6)]
    # Correct DFS nodes: 0 root, 1 after check, 3 after check/bet, 6 after bet.
    def action_probability(k, label):
        return next(a['frequency'] for a in p[k]['actions'] if a['action'] == label)
    s0 = dict(zip(keys0, [action_probability(k, 'bet' if k[0] == 0 else 'call') for k in keys0]))
    s1 = dict(zip(keys1, [action_probability(k, 'bet' if k[0] == 1 else 'call') for k in keys1]))
    def ev(a, b):
        total = 0.0
        for h, q, w in zip(hands, (1, 0), (1/3, 2/3)):
            bet, call = a[0, h], a[3, h]
            vb, vc = b[1, v], b[6, v]
            showdown = 6*q-2
            total += w*((1-bet)*((1-vb)*2*q+vb*call*showdown) + bet*((1-vc)*2+vc*showdown))
        return total
    pure0 = [dict(zip(keys0, x)) for x in itertools.product((0, 1), repeat=len(keys0))]
    pure1 = [dict(zip(keys1, x)) for x in itertools.product((0, 1), repeat=len(keys1))]
    return ev(s0, s1), min(ev(s0, b) for b in pure1), max(ev(a, s1) for a in pure0)


class RiverTests(unittest.TestCase):
    def check_policy(self, result):
        self.assertLessEqual(result['best_response_lower_bb'], result['value_bb']+1e-9)
        self.assertGreaterEqual(result['best_response_upper_bb'], result['value_bb']-1e-9)
        for row in result['policy']:
            self.assertAlmostEqual(sum(a['frequency'] for a in row['actions']), 1)
            for a in row['actions']:
                self.assertTrue(0 <= a['frequency'] <= 1)
                self.assertTrue(a['ev_bb'] is None or math.isfinite(a['ev_bb']))

    def test_polar_oracle(self):
        for n in (50, 100, 500, 1000, 5000):
            t = time.perf_counter()
            r = solve(polar(), iterations=n, pot_bps=())
            elapsed = time.perf_counter()-t
            self.assertEqual(r['nodes'], 9)
            self.check_policy(r)
            for actual, expected in zip((r['value_bb'], r['best_response_lower_bb'], r['best_response_upper_bb']), oracle(r)):
                self.assertAlmostEqual(actual, expected, places=9)
            print(f'polar iterations={n} gap_bb={r["nash_gap_bb"]:.12g} value_bb={r["value_bb"]:.12g} seconds={elapsed:.6f}')
        self.assertLess(r['gap_fraction_of_pot'], .01)

    def test_known_winner_and_loser(self):
        for a, b, expected in ((NUT, CATCH, 2), (CATCH, NUT, 0)):
            r = solve(context([(a, 1)], [(b, 1)]), iterations=1000, pot_bps=())
            self.check_policy(r)
            self.assertAlmostEqual(r['value_bb'], expected, delta=.01)

    def test_tie(self):
        a = 'As 5s Qh Jd Tc'.split()
        b = 'Ah 5h Qs Jc Td'.split()
        r = solve(context([(a, 1)], [(b, 1)], '2c 3d 4h 9s Kc'.split()), iterations=100, pot_bps=())
        self.check_policy(r)
        self.assertLessEqual(r['best_response_lower_bb'], 1)
        self.assertGreaterEqual(r['best_response_upper_bb'], 1)
        self.assertAlmostEqual(r['value_bb'], 1, delta=.001)

    def test_blockers_and_budgets(self):
        c = context([(NUT, 1), (BLUFF, 1)], [(CATCH, 1), (NUT, 1)])
        self.assertEqual(solve(c, iterations=10)['legal_pairs'], 3)
        with self.assertRaises(ValueError):
            solve(context([(NUT, 1)], [(NUT, 1)]))
        for kwargs in ({'node_limit': 1}, {'max_work': 1}, {'iterations': 0}):
            with self.assertRaises(ValueError):
                solve(polar(), **kwargs)
        with self.assertRaises(ValueError):
            solve(dict(polar(), rake_bps=100))

    def test_asymmetric_stack_and_short_raise(self):
        c = context([(NUT, 1)], [(CATCH, 1)], stacks=(20, 3), pot=10, bb=2)
        s = step(start(c), 'BB', 'bet', 2)
        self.assertEqual(bounds(s)['raise_max'], 3)
        s = step(s, 'BTN', 'raise', 3)
        self.assertFalse(bounds(s)['reopened'])
        s = step(s, 'BB', 'call', 1)
        self.assertEqual(s.total_paid, (3, 3))
        self.assertEqual(sum(s.remaining)+s.pot, 33)
        r = solve(c, iterations=1000, pot_bps=())
        self.check_policy(r)
        self.assertAlmostEqual(r['value_bb'], 5, delta=.02)


if __name__ == '__main__':
    unittest.main(verbosity=2)
