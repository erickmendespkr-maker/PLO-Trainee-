import unittest
from fractions import Fraction
from plo5_post_gto_multiway import prior, solve
from plo5_post_gto_multiway_reach import condition_path
from test_plo5_post_gto_multiway import fixture


class ReachTests(unittest.TestCase):
    def test_joint_prior_and_support(self):
        c=fixture(3,2);rows=prior(c)
        joint=[dict(holdings=[list(k) for k in h],weight=w) for h,w in (rows[0],rows[-1])]
        r=solve(c,1,rake_on_fold=False,joint=joint)
        self.assertTrue(all(x['singleton_holdings']==2 for x in r['root_support'].values()))
        p=condition_path(c,r,[],joint=joint)
        self.assertEqual(sum(Fraction(*d['exact_probability']) for d in p['deals']),1)
        with self.assertRaises(ValueError):condition_path(c,r,[])
        self.assertEqual(condition_path(c,r,[],joint=joint,known={'SB':joint[0]['holdings'][0]})['deals'][0]['exact_probability'],[1,1])
    def test_folded_blocker_and_chance_mass(self):
        c=fixture(3,2,4);c['stacks']={'SB':2,'BB':2,'UTG':2};c['pot']=1
        r=solve(c,1,rake_on_fold=False)
        h=[['SB','bet',1],['BB','fold',0],['UTG','call',1]]
        before=condition_path(c,r,h);self.assertEqual(before['status'],'CONDITIONAL_JOINT_RANGE')
        node=next(x for x in r['tree'] if x['history']==h)
        masses=[]
        for card in node['children']:
            a=condition_path(c,r,h+[['chance',card,0]])
            masses.append(Fraction(*a['path_probability']))
            self.assertTrue(all(card not in d['holdings'][1] for d in a['deals']))
        self.assertEqual(sum(masses),Fraction(*before['path_probability']))
    def test_unmodeled_and_missing(self):
        c=fixture(3);r=solve(c,1,rake_on_fold=False)
        self.assertEqual(condition_path(c,r,[['SB','bet',100]])['status'],'UNMODELED_HISTORY')
        r['policy']=[]
        self.assertEqual(condition_path(c,r,[['SB','check',0]])['status'],'INCOMPLETE_POLICY')

if __name__=='__main__':unittest.main()
