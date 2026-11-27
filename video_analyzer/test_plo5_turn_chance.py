import unittest
from fractions import Fraction
from test_plo5_post_gto_river import polar, context, NUT, BLUFF, CATCH, BOARD
from plo5_post_gto_turn_chance import distribution


class TurnChanceTests(unittest.TestCase):
    def test_single_deal(self):
        r=distribution(context([(NUT,1)],[(CATCH,1)],board=BOARD[:4]))
        self.assertEqual((r['legal_pairs'],r['outcomes'],len(r['branches'])),(1,38,38))
        for b in r['branches']:
            self.assertEqual(b['probability'],[1,38]);self.assertNotIn(b['card'],NUT+CATCH+BOARD[:4])
            self.assertEqual(b['joint_deals'][0]['probability'],[1,1])
    def test_weighted_chance_and_marginal_recovery(self):
        c=dict(polar(),board=BOARD[:4]);r=distribution(c)
        total=sum(Fraction(*b['probability']) for b in r['branches']);self.assertEqual(total,1)
        recovered={}
        for b in r['branches']:
            self.assertEqual(sum(Fraction(*d['probability']) for d in b['joint_deals']),1)
            for d in b['joint_deals']:
                h=tuple(d['holdings'][0]);self.assertNotIn(b['card'],sum(d['holdings'],[]))
                recovered[h]=recovered.get(h,0)+Fraction(*b['probability'])*Fraction(*d['probability'])
        self.assertEqual(recovered,{tuple(sorted(NUT)):Fraction(1,3),tuple(sorted(BLUFF)):Fraction(2,3)})
        branch=next(b for b in r['branches'] if b['card']=='As')
        self.assertEqual(branch['probability'],[1,57]);self.assertEqual(branch['joint_deals'][0]['holdings'][0],sorted(BLUFF))
    def test_blockers_and_budget(self):
        c=context([(NUT,1),(BLUFF,1)],[(CATCH,1),(NUT,1)],board=BOARD[:4])
        self.assertEqual(distribution(c)['legal_pairs'],3)
        with self.assertRaises(ValueError):distribution(c,max_outcomes=113)
        with self.assertRaises(ValueError):distribution(polar())
        with self.assertRaises(ValueError):distribution(context([(NUT,1)],[(NUT,1)],board=BOARD[:4]))


if __name__=='__main__':unittest.main(verbosity=2)
