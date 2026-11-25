import copy
import unittest
from plo5_river_solver import solve, prepare

# On this unpaired rainbow board, AA > KK > QQ, no available straight/flush
# with the selected private holdings; the auxiliary cards do not improve rank.
def entry(cards,w=1):return {'cards':cards.split(),'weight':w}

def fixture():
    return dict(variant=5,board='2c 4d 7h 9s Jc'.split(),pot_chips=100,bet_chips=100,hero_stack_chips=200,opponent_stack_chips=200,bb_chips=10,hero_range=[entry('As Ad 3c 5d 8h'),entry('Qs Qd 3s 5h 8d',2)],opponent_range=[entry('Ks Kd 3d 5c 8s')])

class RiverTests(unittest.TestCase):
    def test_polar_equilibrium(self):
        r=solve(fixture(),20000);by={x['cards'][0]:x for x in r['hero_strategy']}
        # Value hand always bets; bluff fraction ~1/4 with twice the bluff mass;
        # villain calls half the time against a pot bet.
        self.assertLess(r['gap_fraction_of_pot'],.02)
        self.assertAlmostEqual(by['3c']['actions'][1]['frequency'],1,delta=.04)
        self.assertAlmostEqual(by['3s']['actions'][1]['frequency'],.25,delta=.04)
        self.assertAlmostEqual(r['opponent_strategy'][0]['call_frequency'],.5,delta=.04)
        self.assertAlmostEqual(r['hero_value_bb'],5,delta=.15)
        self.assertFalse(r['gto_solution']);self.assertFalse(r['production_strategy_authorized'])
    def test_blockers_joint_weights(self):
        g=fixture();g['opponent_range'].append(entry('As Kh 6c Td 8c',3));a,v,pairs,total,mass,p,bb=prepare(g,100)
        self.assertEqual(total,12);self.assertEqual(mass,9);self.assertEqual(len(pairs),3)
        self.assertAlmostEqual(sum(x[2] for x in pairs),1)
    def test_single_known_winner(self):
        g=fixture();g['hero_range']=g['hero_range'][:1];r=solve(g,1000)
        self.assertAlmostEqual(r['hero_value_bb'],10,delta=.02);self.assertLess(r['gap_fraction_of_pot'],.002)
    def test_invalid_and_budget(self):
        for k,v in [('variant',6),('bet_chips',101),('hero_stack_chips',99),('board',['2c']*5),('bb_chips',0)]:
            g=fixture();g[k]=v
            with self.subTest(k=k),self.assertRaises(ValueError):solve(g,1)
        g=fixture();g['hero_range']*=2
        with self.assertRaises(ValueError):solve(g,1)
        with self.assertRaises(ValueError):solve(fixture(),50001)
    def test_deterministic_and_ev_bounds(self):
        a=solve(fixture(),500);self.assertEqual(a,solve(fixture(),500))
        self.assertLessEqual(a['best_response_lower_bb'],a['hero_value_bb']+1e-9);self.assertGreaterEqual(a['best_response_upper_bb'],a['hero_value_bb']-1e-9)
        for h in a['hero_strategy']:self.assertAlmostEqual(sum(x['frequency'] for x in h['actions']),1)

if __name__=='__main__':unittest.main()
