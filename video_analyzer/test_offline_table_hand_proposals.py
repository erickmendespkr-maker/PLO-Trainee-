import unittest
from offline_table_hand_proposals import propose_hand_intervals as run
def obs(t,*states):
    return {'timestamp_seconds':t,'tables':[dict(table_id=i+1,board_state=s,confidence=.9) for i,s in enumerate(states)]}
class Tests(unittest.TestCase):
    def test_empty(self): self.assertEqual(run([])['proposals'],[])
    def test_short(self): self.assertEqual(run([obs(0,'flop')])['proposals'],[])
    def test_basic(self):
        x=run([obs(0,'flop'),obs(2,'turn')])['proposals'][0]
        self.assertEqual(x['board_states_observed'],['flop','turn']); self.assertFalse(x['hand_verified'])
    def test_gap(self): self.assertEqual(len(run([obs(0,'flop'),obs(1,'turn'),obs(30,'river'),obs(31,'river')])['proposals']),2)
    def test_reset(self): self.assertEqual(len(run([obs(0,'turn'),obs(1,'river'),obs(2,'none_visible'),obs(3,'flop')])['proposals']),2)
    def test_four(self): self.assertEqual(len(run([obs(0,*(['flop']*4)),obs(1,*(['turn']*4))])['proposals']),4)
    def test_duplicate(self):
        with self.assertRaises(ValueError): run([{'timestamp_seconds':0,'tables':[dict(table_id=1,board_state='flop',confidence=.5)]*2}])
    def test_timestamp(self):
        with self.assertRaises(ValueError): run([obs(0),obs(0)])
    def test_nan(self):
        with self.assertRaises(ValueError): run([{'timestamp_seconds':0,'tables':[dict(table_id=1,board_state='flop',confidence=float('nan'))]}])
    def test_state(self):
        with self.assertRaises(ValueError): run([obs(0,'preflop')])
    def test_missing_table(self):
        x=run([obs(0,'flop'),obs(1,'turn'),obs(2),obs(3,'river')])
        self.assertEqual(x['proposals'][0]['sample_count'],3)
if __name__=='__main__': unittest.main()
