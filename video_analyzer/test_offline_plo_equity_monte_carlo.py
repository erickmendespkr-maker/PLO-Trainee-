"""Synthetic and independently derived hand-rank tests; no real-session claims."""
import json
from pathlib import Path
import tempfile
import unittest

import offline_plo_equity_monte_carlo as m


class OmahaEquityTests(unittest.TestCase):
    def fixture(self, variant='PLO5', **changes):
        d = {'variant': variant,
             'hero_cards': ['As','Ks','Qs','Js','Ts'] if variant == 'PLO5' else ['As','Ks','Qs','Js','Ts','9s'],
             'board_cards': ['2s','3s','4s','8d','7c'],
             'opponent_model': {'kind':'uniform'}, 'iterations':20, 'seed':123,
             'manual_review_confirmed': True}
        d.update(changes)
        return d

    def test_omaha_uses_exactly_two_hole_cards(self):
        # Three hearts in hand + two on board cannot form a flush in Omaha.
        hero = ('Ah','Kh','Qh','2c','3d')
        board = ('4h','5h','6c','7d','8s')
        self.assertLess(m.omaha_rank(hero, board)[0], 5)

    def test_three_board_cards_mandatory(self):
        # Royal flush on board is not a royal flush without two hearts in hand.
        hero = ('2c','3d','4c','5d','6c')
        board = ('Ah','Kh','Qh','Jh','Th')
        self.assertNotEqual(m.omaha_rank(hero, board)[0], 8)

    def test_wheel_and_straight_flush(self):
        self.assertEqual(m.five_rank(('Ah','2h','3h','4h','5h')), (8,5))
        self.assertEqual(m.five_rank(('Th','Jh','Qh','Kh','Ah')), (8,14))
        self.assertEqual(m.five_rank(('As','2c','3d','4h','5s')), (4,5))

    def test_hand_ordering(self):
        ranks = [
            ('2c','4d','6h','8s','Tc'),
            ('2c','2d','6h','8s','Tc'),
            ('2c','2d','6h','6s','Tc'),
            ('2c','2d','2h','8s','Tc'),
            ('2c','3d','4h','5s','6c'),
            ('2h','4h','6h','8h','Th'),
            ('2c','2d','2h','8s','8c'),
            ('2c','2d','2h','2s','Tc'),
            ('2h','3h','4h','5h','6h'),
        ]
        self.assertEqual([m.five_rank(h)[0] for h in ranks], list(range(9)))
        self.assertEqual(sorted(map(m.five_rank,ranks)), list(map(m.five_rank,ranks)))

    def test_deterministic_seed(self):
        a = m.analyze(self.fixture())
        self.assertEqual(a, m.analyze(self.fixture()))
        self.assertEqual(a['win_count']+a['tie_count']+a['loss_count'],20)
        self.assertTrue(0 <= a['equity_ci95_sampling_only'][0] <= a['equity'] <= a['equity_ci95_sampling_only'][1] <= 1)

    def test_plo6(self):
        a = m.analyze(self.fixture('PLO6'))
        self.assertEqual(a['variant'],'PLO6')
        self.assertTrue(a['exactly_two_hole_three_board_rule'])

    def test_known_certain_win_range(self):
        # Hero has spade royal with exactly 2 spades from hand and 3 from board.
        d = self.fixture(hero_cards=['As','Ks','2c','3d','4c'],
                         board_cards=['Qs','Js','Ts','8d','7c'],
                         opponent_model={'kind':'weighted_combos','combos':[
                             {'cards':['2h','3h','4h','5h','6h'],'weight':1}]})
        a = m.analyze(d)
        self.assertEqual((a['win_count'],a['tie_count'],a['loss_count']),(20,0,0))
        self.assertEqual(a['equity'],1.0)

    def test_known_certain_loss_range(self):
        d = self.fixture(hero_cards=['2c','3d','4c','5d','6c'],
                         board_cards=['Qs','Js','Ts','8d','7c'],
                         opponent_model={'kind':'weighted_combos','combos':[
                             {'cards':['As','Ks','2h','3h','4h'],'weight':1}]})
        a = m.analyze(d)
        self.assertEqual(a['equity'],0.0)

    def test_known_tie_range(self):
        # Both use identical 2-card rank holdings on a board with no flush.
        d = self.fixture(hero_cards=['As','Kd','2c','3d','4c'],
                         board_cards=['Qh','Jh','Tc','8d','7c'],
                         opponent_model={'kind':'weighted_combos','combos':[
                             {'cards':['Ac','Kh','2h','3h','4h'],'weight':1}]})
        a = m.analyze(d)
        self.assertEqual(a['equity'],0.5)
        self.assertEqual(a['tie_count'],20)

    def test_weighted_range_blockers(self):
        d = self.fixture(opponent_model={'kind':'weighted_combos','combos':[
            {'cards':['As','2h','3h','4h','5h'],'weight':3},
            {'cards':['2h','3h','4h','5h','6h'],'weight':2}]})
        a = m.analyze(d)
        self.assertEqual((a['range_eligible_combos'],a['range_blocked_combos']),(1,1))

    def test_call_ev_incremental(self):
        d = self.fixture(hero_cards=['As','Ks','2c','3d','4c'],
                         board_cards=['Qs','Js','Ts','8d','7c'],
                         opponent_model={'kind':'weighted_combos','combos':[
                             {'cards':['2h','3h','4h','5h','6h'],'weight':1}]},
                         pot_now=100,call_cost=20)
        a = m.analyze(d)
        self.assertEqual(a['terminal_call_ev_model']['call_ev_incremental'],100)
        self.assertIsNone(a['terminal_call_ev_model']['raise_ev'])

    def test_no_manual_review(self):
        with self.assertRaises(ValueError): m.analyze(self.fixture(manual_review_confirmed=False))

    def test_reject_duplicate_card(self):
        with self.assertRaises(ValueError): m.analyze(self.fixture(board_cards=['As','3s','4s']))

    def test_reject_duplicate_combo(self):
        combo = {'cards':['2h','3h','4h','5h','6h'],'weight':1}
        with self.assertRaises(ValueError):
            m.analyze(self.fixture(opponent_model={'kind':'weighted_combos','combos':[combo,combo]}))

    def test_reject_nonfinite_weight(self):
        with self.assertRaises(ValueError):
            m.analyze(self.fixture(opponent_model={'kind':'weighted_combos','combos':[
                {'cards':['2h','3h','4h','5h','6h'],'weight':float('nan')}]}))

    def test_reject_bad_seed_bool(self):
        with self.assertRaises(ValueError): m.analyze(self.fixture(seed=True))

    def test_reject_unexpected_claims(self):
        with self.assertRaises(ValueError): m.analyze(self.fixture(ocr_verified=True))

    def test_reject_unsupported_preflop(self):
        with self.assertRaises(ValueError): m.analyze(self.fixture(board_cards=[]))

    def test_json_duplicate_keys_and_nonfinite(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'bad.json'
            p.write_text('{"seed":1,"seed":2}')
            with self.assertRaises(ValueError): m.read_json(p)
            p.write_text('{"seed":NaN}')
            with self.assertRaises(ValueError): m.read_json(p)

    def test_cli_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            src,out = Path(tmp)/'input.json',Path(tmp)/'out.json'
            src.write_text(json.dumps(self.fixture()))
            self.assertEqual(m.main([str(src),str(out)]),0)
            self.assertEqual(json.loads(out.read_text())['iterations'],20)
            with self.assertRaises(ValueError): m.main([str(src),str(out)])


if __name__ == '__main__':
    unittest.main()
