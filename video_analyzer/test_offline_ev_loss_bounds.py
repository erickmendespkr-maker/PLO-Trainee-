import unittest
from offline_ev_loss_bounds import ev_loss_bounds

class EVLossBoundsTests(unittest.TestCase):
    def test_certain_loss(self):
        r = ev_loss_bounds({'tight': {'fold': (0,0), 'call': (3,4)}}, 'fold')
        self.assertEqual(r['per_scenario']['tight'], {'min_ev_loss':3, 'max_ev_loss':4})
    def test_overlap(self):
        r = ev_loss_bounds({'loose': {'fold': (0,0), 'call': (-2,2)}}, 'fold')
        self.assertEqual(r['per_scenario']['loose'], {'min_ev_loss':0, 'max_ev_loss':2})
    def test_chosen_dominates(self):
        r = ev_loss_bounds({'s': {'call': (5,6), 'fold': (0,0)}}, 'call')
        self.assertEqual(r['overall_max_ev_loss'], 0)
    def test_multi_scenario(self):
        r = ev_loss_bounds({'a': {'fold':(0,0),'call':(2,3)}, 'b': {'fold':(0,0),'call':(-2,-1)}}, 'fold')
        self.assertEqual((r['overall_min_ev_loss'],r['overall_max_ev_loss']), (0,3))
    def test_action_mismatch(self):
        with self.assertRaises(ValueError):
            ev_loss_bounds({'a':{'fold':(0,0),'call':(1,2)},'b':{'fold':(0,0),'raise':(1,2)}}, 'fold')
    def test_nan(self):
        with self.assertRaises(ValueError):
            ev_loss_bounds({'a':{'fold':(0,0),'call':(float('nan'),2)}}, 'fold')
    def test_boolean(self):
        with self.assertRaises(ValueError):
            ev_loss_bounds({'a':{'fold':(0,0),'call':(True,2)}}, 'fold')
    def test_missing_chosen(self):
        with self.assertRaises(ValueError):
            ev_loss_bounds({'a':{'fold':(0,0),'raise':(1,2)}}, 'call')
    def test_empty(self):
        with self.assertRaises(ValueError): ev_loss_bounds({}, 'fold')
    def test_inverted(self):
        with self.assertRaises(ValueError):
            ev_loss_bounds({'a':{'fold':(0,0),'call':(2,1)}}, 'fold')

if __name__ == '__main__': unittest.main()
