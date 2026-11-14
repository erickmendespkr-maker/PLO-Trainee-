"""Synthetic regression checks for offline PLO5/PLO6 known-card showdown."""
import unittest
from .offline_omaha_showdown import omaha_rank, showdown_shares

class TestOfflineOmahaShowdown(unittest.TestCase):
    def test_board_royal_is_not_royal(self):
        self.assertNotEqual(omaha_rank(['2c','3d','4c','5d','6c'],['As','Ks','Qs','Js','Ts'])[0], 8)

    def test_exactly_two_hole_for_royal(self):
        self.assertEqual(omaha_rank(['As','Ks','2c','3d','4h'],['Qs','Js','Ts','9d','8c']), (8,14))

    def test_plo6(self):
        self.assertEqual(omaha_rank(['As','Ks','2c','3d','4h','5h'],['Qs','Js','Ts','9d','8c']), (8,14))

    def test_wheel(self):
        self.assertEqual(omaha_rank(['Ac','2d','9c','Tc','Jc'],['3s','4h','5d','Kd','Qc'])[0], 4)

    def test_tie(self):
        self.assertEqual(showdown_shares([['Ac','6d','Td','Jh','Qs'],['Ad','6c','Th','Jd','Qh']],['2c','3d','4h','5s','9c']), [.5,.5])

    def test_win_loss(self):
        self.assertEqual(showdown_shares([['Ac','6d','Td','Jh','Qs'],['Kd','Qc','Th','Jd','8h']],['2c','3d','4h','5s','9c']), [1.,0.])

    def test_cross_player_duplicates(self):
        with self.assertRaises(ValueError):
            showdown_shares([['Ac','6d','Td','Jh','Qs'],['Ac','Qc','Th','Jd','8h']],['2c','3d','4h','5s','9c'])

    def test_overlap(self):
        with self.assertRaises(ValueError):
            omaha_rank(['As','Ks','2c','3d','4h'],['As','Js','Ts','9d','8c'])

    def test_invalid_count(self):
        with self.assertRaises(ValueError):
            omaha_rank(['As','Ks','2c','3d'],['Qs','Js','Ts','9d','8c'])
