import os
import unittest
import tempfile
from pathlib import Path
from fractions import Fraction
from plo5_decision_math import equity,evaluate_model,snapshot_metrics,review_snapshots
from plo5_post_gto_multiway import solve
from test_plo5_post_gto_river import polar,context,NUT,BLUFF,CATCH,BOARD
from test_plo5_snapshot_replay import seed,snap,manifest,B,H,V


def all_bet(c):
    r=solve(c,1,rake_on_fold=False)
    for p in r['policy']:
        if p['node']==0:
            for a in p['actions']:a['frequency']=float(a['action']=='bet')
    return r

class DecisionMathTests(unittest.TestCase):
    def test_exact_weighted_river(self):
        c=polar();r=all_bet(c);e=equity(c,r,[['BB','bet',2]],CATCH)
        self.assertEqual(e['equity'],[2,3]);self.assertEqual(e['terminal_ev']['actions'],{'fold:0':[0,1],'call:2':[2,1]})
        self.assertFalse(e['gto_solution'])
    def test_rake_and_native_rank(self):
        c=polar();c['rake_bps']=5000;c['rake_cap']=2;r=all_bet(c);h=[['BB','bet',2]];e=equity(c,r,h,CATCH)
        self.assertEqual(e['terminal_ev']['actions']['call:2'],[2,3])
        exe=os.environ.get('PLO5_RANK_WORKER_EXE')
        if exe:
            from plo5_rank_worker import RankWorker
            with RankWorker(exe) as w:a=equity(c,r,h,CATCH,rank_worker=w)
            self.assertEqual(dict(a,rank_backend='python'),e)
    def test_turn_exact_runouts(self):
        c=context([(NUT,1)],[(CATCH,1)],board=BOARD[:4]);r=all_bet(c)
        e=equity(c,r,[['BB','bet',2]],CATCH)
        self.assertEqual(e['runouts'],38);self.assertEqual(e['equity'],[0,1]);self.assertEqual(e['terminal_ev']['actions']['call:2'],[-2,1])
        with self.assertRaisesRegex(ValueError,'runout budget'):equity(c,r,[['BB','bet',2]],CATCH,max_runouts=37)
    def test_native_cfr_cache(self):
        m=dict(context=polar(),history=[['BB','bet',2]],holding=CATCH,action=['call',2],rake_on_fold=False,iterations=100)
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'c.sqlite';a=evaluate_model(p,m,cfr_executable=os.environ.get('PLO5_MULTIWAY_EXE'));b=evaluate_model(p,m,cfr_executable=os.environ.get('PLO5_MULTIWAY_EXE'))
            self.assertFalse(a['cache_hit']);self.assertTrue(b['cache_hit']);self.assertEqual(a['equity'],b['equity']);self.assertFalse(a['strategy_verified'])
    def test_snapshot_prefix(self):
        rows=[snap(0,3,39,38,'hero_bottom'),snap(1,4,38,38,'top'),snap(2,4,38,38,None),snap(3,4,38,38,'top',B[:3],True),snap(4,4,38,38,'hero_bottom',B[:3]),snap(5,4,38,38,None,B[:3])]
        r=snapshot_metrics(manifest(rows),seed(),rows,['flop']);self.assertEqual(len(r['metrics']),1);self.assertEqual(r['metrics'][0]['hu_spr_street_start'],9.5);self.assertEqual(r['selection']['evaluated'],1);self.assertFalse(r['selection']['print_requests'])
    def test_snapshot_to_native_flop(self):
        sd=seed();sd['initial']={'hero_bottom':4,'top':4}
        rows=[snap(0,3,3,2,'hero_bottom'),snap(1,4,2,2,'top'),snap(2,4,2,2,None),snap(3,4,2,2,'top',B[:3],True),snap(4,6,2,0,'hero_bottom',B[:3]),snap(5,8,0,0,None,B[:3])]
        ranges={'SB':[dict(cards=H,weight=1)],'BB':[dict(cards=V,weight=1)]}
        with tempfile.TemporaryDirectory() as t:
            r=review_snapshots(Path(t)/'cache.sqlite',manifest(rows),sd,rows,ranges=ranges,rake_bps=0,rake_cap=0,rake_on_fold=False,streets=['flop'],iterations=1,cfr_executable=os.environ.get('PLO5_MULTIWAY_EXE'))
            self.assertEqual(len(r['estimates']),1);e=r['estimates'][0];self.assertEqual(e['status'],'EXPERIMENTAL_MODEL_ONLY');self.assertEqual(e['estimate']['state']['board'],B[:3]);self.assertEqual(e['estimate']['equity']['runouts'],741);self.assertFalse(r['selection']['print_requests'])
    def test_own_zero_frequency_does_not_erase_context(self):
        c=polar();r=all_bet(c)
        node=next(x['node'] for x in r['tree'] if x['history']==[['BB','check',0]])
        for p in r['policy']:
            if p['node']==node:
                for a in p['actions']:a['frequency']=float(a['action']=='bet')
        e=equity(c,r,[['BB','check',0],['BTN','bet',2]],NUT)
        self.assertEqual(e['equity'],[1,1]);self.assertEqual(e['path_probability_scope'],'interventional');self.assertEqual(e['intervened_seat'],'BB')
    def test_zero_path(self):
        c=polar();r=all_bet(c);e=equity(c,r,[['BB','check',0]],CATCH);self.assertEqual(e['status'],'ZERO_PATH_LIKELIHOOD');self.assertIsNone(e['equity'])
if __name__=='__main__':unittest.main()
