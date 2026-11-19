import unittest
from video_analyzer.pokerinfra_bridge import request,pot_odds_and_call_ev

class BridgeTests(unittest.TestCase):
    def test_plo5(self):
        self.assertEqual(len(request('evaluate','PLO5',hole=['Ah','Kd','Qc','Js','Th'],board=['2c','3d','4h'])['hole']),5)
    def test_plo6(self):
        self.assertEqual(request('equity','PLO6',holes=[['Ah','Kd','Qc','Js','Th','9d'],[]],seed=17)['request']['method']['seed'],17)
    def test_duplicate(self):
        with self.assertRaises(ValueError): request('evaluate','PLO5',hole=['Ah','Kd','Qc','Js','Th'],board=['Ah','3d','4h'])
    def test_invalid_count(self):
        with self.assertRaises(ValueError): request('evaluate','PLO6',hole=['Ah','Kd','Qc','Js','Th'],board=[])
    def test_showdown(self):
        self.assertEqual(len(request('showdown','PLO',holes=[['Ah','Kd','Qc','Js'],['2h','3d','4c','5s']],board=['6h','7d','8c','9s','Tc'])['holes']),2)
    def test_ev(self):
        self.assertAlmostEqual(pot_odds_and_call_ev(90,30,.28)['call_ev_bb'],3.6)
    def test_invalid_operation(self):
        with self.assertRaises(ValueError): request('solve','PLO5')
    def test_invalid_variant(self):
        with self.assertRaises(ValueError): request('evaluate','NLH',hole=[],board=[])
    def test_invalid_board(self):
        with self.assertRaises(ValueError): request('evaluate','PLO5',hole=['Ah','Kd','Qc','Js','Th'],board=['2c'])
