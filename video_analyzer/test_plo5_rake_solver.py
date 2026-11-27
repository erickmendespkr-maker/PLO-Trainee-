import itertools
import json
import tempfile
import unittest
from pathlib import Path
from test_plo5_post_gto_river import polar, NUT, BLUFF, CATCH
from plo5_post_gto_river import solve as zero
from plo5_post_gto_rake_solver import solve
from plo5_post_gto_store import solve_cached, lookup
from plo5_rake_presets import profile, apply, save, load
from plo5_rake_gui import solve_file


def oracle(r,bps,cap,fold):
    # Independent cash flows for pot=2, stacks=2, nine-node polar game.
    # Pure-plan enumeration for each seat, no production settlement or tree calls.
    h=[tuple(sorted(x)) for x in (NUT,BLUFF)];v=tuple(sorted(CATCH))
    rows={(x['node'],tuple(x['holding'])):x for x in r['policy']}
    def pr(n,k,label):return next(a['frequency'] for a in rows[n,k]['actions'] if a['action']==label)
    a=[pr(0,k,'bet') for k in h]+[pr(3,k,'call') for k in h]
    b=[pr(1,v,'bet'),pr(6,v,'call')]
    def net(pot,folded):return pot-min(cap,pot*bps//10000) if not folded or fold else pot
    def ev(a,b):
        val=[0.,0.]
        for i,q,w in ((0,1,1/3),(1,0,2/3)):
            terms=[((1-a[i])*(1-b[0]),(q*net(2,False),(1-q)*net(2,False))),
                   ((1-a[i])*b[0]*(1-a[2+i]),(0,net(2,True))),
                   ((1-a[i])*b[0]*a[2+i],(q*net(6,False)-2,(1-q)*net(6,False)-2)),
                   (a[i]*(1-b[1]),(net(2,True),0)),
                   (a[i]*b[1],(q*net(6,False)-2,(1-q)*net(6,False)-2))]
            for p,pay in terms:
                for j in (0,1):val[j]+=w*p*pay[j]
        return val
    return ev(a,b),[max(ev(x,b)[0] for x in itertools.product((0,1),repeat=4)),max(ev(a,y)[1] for y in itertools.product((0,1),repeat=2))]


class RakeTests(unittest.TestCase):
    def test_independent_oracle(self):
        for bps,cap in ((0,0),(5000,3),(5000,1),(10000,10)):
            for fold in (False,True):
                r=solve(dict(polar(),rake_bps=bps,rake_cap=cap),500,(),rake_on_fold=fold)
                values,best=oracle(r,bps,cap,fold)
                for a,b in zip(r['values_bb']+r['best_responses_bb'],values+best):self.assertAlmostEqual(a,b,places=9)
                self.assertAlmostEqual(r['nashconv_bb'],sum(b-a for a,b in zip(values,best)),places=9)
                self.assertAlmostEqual(sum(values)+r['expected_rake_bb'],2,places=9)
    def test_zero_rake_parity(self):
        r=solve(polar(),1000,(),rake_on_fold=False);z=zero(polar(),1000,())
        self.assertAlmostEqual(r['values_bb'][0],z['value_bb'],places=9)
        self.assertAlmostEqual(r['nashconv_bb'],z['nash_gap_bb'],places=9)
        for x,y in zip(r['policy'],z['policy']):
            for a,b in zip(x['actions'],y['actions']):
                self.assertAlmostEqual(a['frequency'],b['frequency'],places=8)
                self.assertAlmostEqual(a['ev_bb'],b['ev_bb'],places=8)
    def test_rake_changes_policy(self):
        a=solve(polar(),1000,(),rake_on_fold=False)
        b=solve(dict(polar(),rake_bps=5000,rake_cap=3),1000,(),rake_on_fold=False)
        self.assertGreater(b['expected_rake_bb'],0)
        self.assertGreater(max(abs(x['frequency']-y['frequency']) for p,q in zip(a['policy'],b['policy']) for x,y in zip(p['actions'],q['actions'])),.1)
    def test_presets_and_cache(self):
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/'cache.db';p=profile('PPPoker','Clube A','PLO5','5,25','2',False)
            save(path,p);self.assertEqual(load(path),[p]);c,fold=apply(polar(),p)
            self.assertEqual((c['rake_bps'],c['rake_cap'],fold),(525,2,False))
            a=solve_cached(path,c,50,(),rake_on_fold=fold);b=solve_cached(path,c,50,(),rake_on_fold=fold)
            self.assertTrue(b['cache_hit']);self.assertNotEqual(a['model_key'],solve_cached(path,c,50,(),rake_on_fold=True)['model_key'])
            self.assertNotEqual(a['model_key'],solve_cached(path,dict(c,rake_bps=1000),50,(),rake_on_fold=False)['model_key'])
            self.assertEqual(lookup(b,[],NUT)['status'],'CONDITIONAL_POLICY')
            source=Path(t)/'context.json';source.write_text(json.dumps(polar()))
            self.assertEqual(solve_file(source,path,p,50)['result']['rake_bps'],525)
    def test_invalid_presets(self):
        for percent in ('NaN','-1','100.01','0.001','1e-100000'):
            with self.assertRaises(ValueError):profile('P','C','L',percent,'2',False)
        with self.assertRaises(ValueError):apply(polar(),profile('P','C','L','5','0.5',False))
        with self.assertRaises(ValueError):solve_cached(':memory:',dict(polar(),rake_bps=500),50,(),rake_on_fold=None)


if __name__=='__main__':unittest.main(verbosity=2)
