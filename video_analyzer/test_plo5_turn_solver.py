import unittest
import os
import subprocess
from fractions import Fraction
from test_plo5_post_gto_river import context, polar, NUT, BLUFF, CATCH, BOARD
from plo5_post_gto_turn_solver import solve
from plo5_post_gto_context import DECK
from offline_omaha_showdown import omaha_rank


class TurnSolverTests(unittest.TestCase):
    def test_public_infosets_and_chance(self):
        c=dict(polar(),board=BOARD[:4]); r=solve(c,1,rake_on_fold=False)
        self.assertEqual(r['chance_outcomes'],76)
        root=[p for p in r['policy'] if p['node']==0]
        self.assertEqual(len(root),2)
        self.assertEqual({tuple(p['holding']) for p in root},{tuple(sorted(NUT)),tuple(sorted(BLUFF))})
        for p in r['policy']:
            s=r['tree'][p['node']]
            self.assertFalse(set(p['holding'])&set(s['board']))
            self.assertAlmostEqual(sum(a['frequency'] for a in p['actions']),1)
            if len(s['board'])==4:self.assertFalse(any(x[0]=='chance' for x in s['history']))
            else:self.assertEqual([x[1] for x in s['history'] if x[0]=='chance'],[s['board'][-1]])
        for s in r['tree']:
            if s['status']=='chance_transition':
                self.assertEqual(len(s['children']),43) # 38 per pair, 5 distinct blocked cards
                for card,k in s['children'].items():self.assertEqual(r['tree'][k]['board'],s['board']+[card])
    def test_allin_action_ev_independent(self):
        for bps,cap in ((0,0),(5000,3)):
            c=dict(polar(),board=BOARD[:4],rake_bps=bps,rake_cap=cap)
            r=solve(c,1,rake_on_fold=False)
            for h in (NUT,BLUFF):
                shares=[]
                for card in sorted(DECK-set(h)-set(CATCH)-set(c['board'])):
                    board=c['board']+[card];a,b=omaha_rank(h,board),omaha_rank(CATCH,board)
                    shares.append(Fraction(1) if a>b else Fraction(1,2) if a==b else Fraction(0))
                self.assertEqual(len(shares),38)
                eq=sum(shares)/38
                # Uniform villain fold/call, root bet all-in 2, net pot 6 on call.
                expected=(2+eq*(6-min(cap,6*bps//10000))-2)/2
                row=next(p for p in r['policy'] if p['node']==0 and p['holding']==sorted(h))
                actual=next(a['ev_bb'] for a in row['actions'] if a['action']=='bet')
                self.assertAlmostEqual(actual,float(expected),places=9)
    def test_convergence_and_rake(self):
        c=dict(polar(),board=BOARD[:4]);a=solve(c,1,rake_on_fold=False);b=solve(c,100,rake_on_fold=False)
        self.assertLess(b['nashconv_bb'],a['nashconv_bb'])
        self.assertAlmostEqual(sum(b['values_bb']),2,places=9)
        for fold in (False,True):
            r=solve(dict(c,rake_bps=5000,rake_cap=3),30,rake_on_fold=fold)
            self.assertGreater(r['expected_rake_bb'],0)
            self.assertAlmostEqual(sum(r['values_bb'])+r['expected_rake_bb'],2,places=9)
            self.assertTrue(all(x>=0 for x in r['unilateral_gains_bb']))
    @unittest.skipUnless(os.environ.get('PLO5_MULTISTREET_EXE'),'native executable not provided')
    def test_native_parity(self):
        exe=os.environ['PLO5_MULTISTREET_EXE']
        for bps,cap,fold in ((0,0,False),(5000,3,False),(5000,3,True)):
            c=dict(polar(),board=BOARD[:4],rake_bps=bps,rake_cap=cap)
            for n in (1,20,100):
                a=solve(c,n,rake_on_fold=fold);b=solve(c,n,rake_on_fold=fold,cfr_executable=exe)
                self.assertEqual(b['backend'],'native');self.assertEqual(a['tree'],b['tree'])
                for x,y in zip(a['values_bb']+a['best_responses_bb'],b['values_bb']+b['best_responses_bb']):self.assertAlmostEqual(x,y,delta=1e-8)
                self.assertEqual(len(a['policy']),len(b['policy']))
                for x,y in zip(a['policy'],b['policy']):
                    self.assertEqual((x['node'],x['holding']),(y['node'],y['holding']))
                    for u,v in zip(x['actions'],y['actions']):
                        self.assertAlmostEqual(u['frequency'],v['frequency'],delta=1e-8)
                        if u['ev_bb'] is None:self.assertIsNone(v['ev_bb'])
                        else:self.assertAlmostEqual(u['ev_bb'],v['ev_bb'],delta=1e-8)
        for payload in ('0 1 1 1\n','3 1 1 1\n0 1\n0 0 2 1 1\n','1 1 1 1\n0 1\n-1 0 0\n'):
            r=subprocess.run([exe],input=payload,text=True,capture_output=True,timeout=5)
            self.assertNotEqual(r.returncode,0)

    def test_invalid_context_and_budgets(self):
        c=dict(polar(),board=BOARD[:4])
        for kwargs in (dict(max_pairs=1),dict(node_limit=2),dict(max_work=10),dict(iterations=0)):
            with self.assertRaises(ValueError):solve(c,rake_on_fold=False,**kwargs)
        with self.assertRaises(ValueError):solve(polar(),rake_on_fold=False)
        with self.assertRaises(ValueError):solve(context([(NUT,1)],[(NUT,1)],board=BOARD[:4]),rake_on_fold=False)


if __name__=='__main__':unittest.main(verbosity=2)
