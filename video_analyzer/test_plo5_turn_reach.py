import unittest
from fractions import Fraction
from test_plo5_post_gto_river import polar, BOARD, NUT, BLUFF
from plo5_post_gto_turn_solver import solve
from plo5_post_gto_turn_reach import condition_path


class ReachTests(unittest.TestCase):
    def setUp(self):
        self.c=dict(polar(),board=BOARD[:4]);self.r=solve(self.c,1,rake_on_fold=False)
    def test_chance_after_actions(self):
        h=[['BB','check',0],['BTN','check',0]]
        before=condition_path(self.c,self.r,h)
        self.assertEqual(before['path_probability'],[1,4]);self.assertEqual(len(before['deals']),2)
        after=condition_path(self.c,self.r,h+[['chance','As',0]])
        self.assertEqual(after['path_probability'],[1,228]);self.assertEqual(len(after['deals']),1)
        self.assertEqual(after['deals'][0]['holdings'][0],sorted(BLUFF))
        self.assertEqual(after['deals'][0]['exact_probability'],[1,1])
        self.assertEqual(condition_path(self.c,self.r,h+[['chance','As',0]],known={'BB':NUT})['status'],'ZERO_PATH_LIKELIHOOD')
    def test_probability_conservation(self):
        h=[['BB','check',0],['BTN','check',0]]
        node=next(x for x in self.r['tree'] if x['history']==h)
        total=sum(Fraction(*condition_path(self.c,self.r,h+[['chance',card,0]])['path_probability']) for card in node['children'])
        self.assertEqual(total,Fraction(1,4))
    def test_invalid_and_missing(self):
        self.assertEqual(condition_path(self.c,self.r,[['chance','As',0]])['status'],'UNMODELED_HISTORY')
        self.r['policy']=[]
        self.assertEqual(condition_path(self.c,self.r,[['BB','check',0]])['status'],'INCOMPLETE_POLICY')
        with self.assertRaises(ValueError):condition_path(dict(self.c,pot=3),self.r,[])


if __name__=='__main__':unittest.main(verbosity=2)
