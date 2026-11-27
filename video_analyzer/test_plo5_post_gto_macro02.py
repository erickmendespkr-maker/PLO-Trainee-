import copy
from contextlib import closing
from fractions import Fraction
import os
import sqlite3
import tempfile
import unittest
from test_plo5_post_gto_river import context, polar, NUT, CATCH, BLUFF
from plo5_post_gto_tree import start, step
from plo5_post_gto_store import solve_cached, lookup, specification
from plo5_post_gto_joint_ranges import condition_path, exact_integer_weights
from plo5_post_gto_rake import settle


class Macro02Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name,'test.sqlite')

    def test_cache_reopen_and_lookup(self):
        a = solve_cached(self.path,polar(),100,())
        b = solve_cached(self.path,polar(),100,())
        self.assertFalse(a.pop('cache_hit'))
        self.assertTrue(b.pop('cache_hit'))
        self.assertEqual(a,b)
        self.assertEqual(lookup(b,[],NUT)['status'],'CONDITIONAL_POLICY')
        self.assertEqual(lookup(b,[dict(action='bet',amount=1,position='BB')],CATCH)['status'],'UNMODELED_HISTORY')
        self.assertEqual(lookup(b,[],CATCH)['status'],'UNMODELED_HOLDING_OR_TERMINAL')
        for row in b['tree']:
            for action in row['actions']:
                self.assertEqual(b['tree'][action['child']]['history'],row['history']+[{k:v for k,v in action.items() if k!='child'}])
        with self.assertRaises(ValueError):
            solve_cached(self.path,polar(),100,(),node_limit=1)

    def test_identity(self):
        c = polar()
        a = specification(c,100,(5000,10000))[0]
        self.assertEqual(a,specification(c,100,(10000,5000,5000))[0])
        self.assertNotEqual(a,specification(c,101,(5000,10000))[0])
        self.assertNotEqual(a,specification(c,100,())[0])
        self.assertNotEqual(a,specification(dict(c,pot=3),100,(5000,10000))[0])
        d = copy.deepcopy(c)
        d['ranges']['BB'].reverse()
        self.assertEqual(a,specification(d,100,(5000,10000))[0])

    def test_corrupt_cache(self):
        solve_cached(self.path,polar(),100,())
        with closing(sqlite3.connect(self.path)) as con, con:
            con.execute("UPDATE river_cache_v1 SET payload='{}'")
        with self.assertRaisesRegex(ValueError,'checksum'):
            solve_cached(self.path,polar(),100,())

    def test_joint_conditioning(self):
        c = polar()
        d = solve_cached(self.path,c,100,())
        root = condition_path(c,d,[])
        self.assertEqual(sorted(Fraction(*x['exact_probability']) for x in root['deals']),[Fraction(1,3),Fraction(2,3)])
        h = [dict(position='BB',action='bet',amount=2)]
        post = condition_path(c,d,h)
        self.assertEqual(post['status'],'CONDITIONAL_JOINT_RANGE')
        expected = {}
        for holding,w in ((NUT,1),(BLUFF,2)):
            row = lookup(d,[],holding)['policy']
            f = next(x['frequency'] for x in row['actions'] if x['action']=='bet')
            expected[tuple(sorted(holding))] = w*Fraction(str(f))
        total = sum(expected.values())
        self.assertEqual(Fraction(*post['action_probability']),total/3)
        for deal in post['deals']:
            self.assertEqual(Fraction(*deal['exact_probability']),expected[tuple(deal['holdings'][0])]/total)
        self.assertEqual(len(condition_path(c,d,[],known={'BB':NUT})['deals']),1)
        self.assertEqual(condition_path(c,d,[dict(position='BB',action='bet',amount=1)])['status'],'UNMODELED_HISTORY')
        with self.assertRaises(ValueError):
            condition_path(dict(c,pot=3),d,[])

    def test_joint_blockers_and_missing_policy(self):
        c = context([(NUT,1),(BLUFF,1)],[(CATCH,1),(NUT,1)])
        d = solve_cached(self.path,c,10,())
        root = condition_path(c,d,[])
        self.assertEqual(len(root['deals']),3)
        self.assertTrue(all(not set(x['holdings'][0])&set(x['holdings'][1]) for x in root['deals']))
        d['result']['policy']=[]
        self.assertEqual(condition_path(c,d,[dict(position='BB',action='bet',amount=2)])['status'],'INCOMPLETE_POLICY')

    def test_exact_weights(self):
        rows=[dict(cards=NUT,exact_probability=[1,3]),dict(cards=BLUFF,exact_probability=[2,3])]
        self.assertEqual([r['weight'] for r in exact_integer_weights(rows)['rows']],[1,2])
        self.assertEqual(exact_integer_weights(rows,1)['status'],'EXACT_WEIGHT_BUDGET_EXCEEDED')
        with self.assertRaises(ValueError):
            exact_integer_weights(rows[:1])

    @unittest.skipUnless(os.environ.get('PLO5_CFR_EXE'), 'native executable not supplied')
    def test_native_cache(self):
        exe=os.environ['PLO5_CFR_EXE']
        a=solve_cached(self.path,polar(),100,(),cfr_executable=exe)
        b=solve_cached(self.path,polar(),100,(),cfr_executable=exe)
        py=solve_cached(self.path,polar(),100,())
        self.assertTrue(b['cache_hit'])
        self.assertFalse(py['cache_hit'])
        self.assertNotEqual(py['model_key'],a['model_key'])
        self.assertAlmostEqual(py['result']['value_bb'],a['result']['value_bb'],delta=1e-8)

    def test_joint_two_actions(self):
        c=polar()
        d=solve_cached(self.path,c,1,())
        h=[dict(position='BB',action='check',amount=0),dict(position='BTN',action='bet',amount=2)]
        r=condition_path(c,d,h)
        self.assertEqual(Fraction(*r['action_probability']),Fraction(1,4))
        self.assertEqual(sorted(Fraction(*x['exact_probability']) for x in r['deals']),[Fraction(1,3),Fraction(2,3)])
        for row in d['result']['policy']:
            if row['node']==0:
                for action in row['actions']:
                    action['frequency']=int(action['action']=='bet')
        self.assertEqual(condition_path(c,d,h)['status'],'ZERO_ACTION_LIKELIHOOD')

    def test_cache_budget_and_rake_rejection(self):
        solve_cached(self.path,polar(),100,())
        with self.assertRaises(ValueError):
            solve_cached(self.path,polar(),100,(),max_work=1)
        with self.assertRaises(ValueError):
            solve_cached(self.path,dict(polar(),rake_bps=100),100,())

    def test_rake_ledger(self):
        c=context([(NUT,1)],[(CATCH,1)],stacks=(20,3),pot=10,bb=2)
        s=step(start(c),'BB','bet',10)
        s=step(s,'BTN','call',3)
        for q in (0,Fraction(1,2),1):
            r=settle(s,q,1000,5,rake_on_fold=False)
            self.assertEqual(r['returned'],(7,0))
            self.assertEqual(r['contested'],16)
            self.assertEqual(r['rake'],1)
            self.assertEqual(sum(r['awards'])+sum(r['returned'])+r['rake'],s.pot)
            self.assertEqual(sum(r['utility_chips'])+r['rake'],10)
        s=step(start(c),'BB','bet',10)
        s=step(s,'BTN','fold',0)
        self.assertEqual(settle(s,0,1000,5,rake_on_fold=False)['rake'],0)
        self.assertEqual(settle(s,0,1000,5,rake_on_fold=True)['rake'],1)
        self.assertEqual(settle(s,0,1000,0,rake_on_fold=True)['rake'],0)


if __name__=='__main__':
    unittest.main(verbosity=2)
