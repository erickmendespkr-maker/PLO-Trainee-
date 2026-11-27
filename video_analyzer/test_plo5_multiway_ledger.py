import unittest
from fractions import Fraction
from random import Random
from plo5_post_gto_multiway_ledger import settle


class LedgerTests(unittest.TestCase):
    def test_main_side_and_return(self):
        r=settle(30,[10,20,40],[False]*3,[(8,),(7,),(6,)],rake_on_fold=False)
        self.assertEqual(r['awards'],[60,20,0]);self.assertEqual(r['returned'],[0,0,20]);self.assertEqual(r['utility_chips'],[50,0,-20])
    def test_tie_and_folded_block(self):
        r=settle(30,[10,20,20,10],[False,False,False,True],[(8,),(8,),(7,),None],rake_on_fold=False)
        self.assertEqual(r['awards'],[35,55,0,0])
        self.assertEqual(r['layers'][1]['eligible'],[0,1,2]);self.assertEqual(r['layers'][2]['eligible'],[1,2])
    def test_rake_proportional(self):
        r=settle(30,[10,20,40],[False]*3,[(8,),(7,),(6,)],1000,5,rake_on_fold=False)
        self.assertEqual(r['rake'],5);self.assertEqual(r['awards'],[Fraction(225,4),Fraction(75,4),0]);self.assertEqual(sum(r['utility_chips']),25)
    def test_fold(self):
        for fold,fee in ((False,0),(True,4)):
            r=settle(10,[10,10,20],[True,True,False],[None,None,None],1000,10,rake_on_fold=fold)
            self.assertEqual(r['rake'],fee);self.assertEqual(r['awards'],[0,0,40-fee]);self.assertEqual(r['returned'],[0,0,10])
    def test_random_conservation(self):
        rng=Random(27112026)
        for n in range(2,7):
            for _ in range(100):
                paid=[rng.randrange(0,101) for _ in range(n)];ranks=[(rng.randrange(9),) for _ in range(n)]
                # All live to construct feasible synthetic showdown fixtures.
                r=settle(30,paid,[False]*n,ranks,500,7,rake_on_fold=False)
                self.assertEqual(sum(r['awards'])+sum(r['returned'])+r['rake'],30+sum(paid))
                self.assertEqual(sum(r['utility_chips'])+r['rake'],30)
    def test_invalid(self):
        for paid,folded in (([1,2],[True,True]),([1,2],[False,True]),([1,2,2],[False,True,True])):
            with self.assertRaises(ValueError):settle(10,paid,folded,[(1,)]*len(paid),rake_on_fold=False)

if __name__=='__main__':unittest.main()
