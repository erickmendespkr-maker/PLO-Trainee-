import os
import tempfile
import unittest
from pathlib import Path
from hashlib import sha256
from PIL import Image
from test_plo5_post_gto_river import polar, context,NUT,BLUFF,CATCH,BOARD
from test_plo5_pre_post_bridge import fixture
from test_plo5_pre_policy_bridge import export_fixture
from test_plo5_reconstruction_candidates import frame
from plo5_review import postflop,preflop,from_preflop,visual,declared_settlement
from plo5_review_html import render,write


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.cache=self.root/'cache.db'
    def test_model_ev_and_cache(self):
        c=polar();hist=[['BB','bet',2]]
        r=postflop(self.cache,c,hist,CATCH,['call',2],rake_on_fold=False,iterations=100)
        self.assertEqual(r['position'],'BTN');self.assertAlmostEqual(r['pot_odds_gross'],1/3)
        self.assertAlmostEqual(r['ev_gap_bb'],max(a['ev_bb'] for a in r['actions'])-r['ev_bb'])
        a=postflop(self.cache,c,hist,CATCH,['fold',0],rake_on_fold=False,iterations=100)
        self.assertTrue(a['cache_hit']);self.assertAlmostEqual(a['ev_bb'],0);self.assertFalse(a['gto_solution'])
        self.assertIn('Pot odds',render(r));self.assertIn('<details>',render(r))
    def test_unmodeled_action_and_invalid(self):
        c=context([(NUT,1)],[(CATCH,1)],stacks=(4,4),pot=4)
        r=postflop(self.cache,c,[],NUT,['bet',2],rake_on_fold=False,iterations=5)
        self.assertEqual(r['status'],'UNMODELED_ACTION');self.assertIsNone(r['ev_bb'])
        with self.assertRaises(ValueError):postflop(self.cache,c,[],NUT,['bet',99],rake_on_fold=False)
        with self.assertRaises(ValueError):postflop(self.cache,c,[],BLUFF,['check',0],rake_on_fold=False)
    def test_rank_native(self):
        index=os.environ.get('PLO5_INDEX_EXE');rank=os.environ.get('PLO5_RANK_EXE')
        if not index or not rank:self.skipTest('native index/rank absent')
        r=postflop(self.cache,polar(),[],NUT,['bet',2],rake_on_fold=False,iterations=5,rank_executables=(index,rank),cfr_executable=os.environ.get('PLO5_MULTIWAY_EXE'))
        self.assertEqual(r['rank']['source'],'NATIVE_COMPUTED');self.assertTrue(1<=r['rank']['rank']<=7462)
    def test_preflop_bridge(self):
        c,_=fixture();p=export_fixture(c);r=preflop(c,p)
        self.assertEqual(r['status'],'PREFLOP_POLICY_UNVERIFIED_PRIOR');self.assertIsNone(r['ev_bb'])
        r=from_preflop(self.cache,c,p,BOARD[:3],[],CATCH,['check',0],iterations=1,cfr_executable=os.environ.get('PLO5_MULTIWAY_EXE'))
        self.assertFalse(r['training_context_verified']);self.assertIsNotNone(r['ev_bb']);self.assertIn('Origem pré-flop',render(r))
    def test_visual_report_and_image_integrity(self):
        a,b=frame(0),frame(1,'90');r=visual(dict(variant=5,hands_reconstructed=False,frames=[a,b]))
        self.assertIsNone(r['ev_bb']);self.assertEqual(len(r['changes']),1)
        p=self.root/'frame.png';Image.new('RGB',(10,10)).save(p)
        f=dict(file=p.name,pts='1',sha256=sha256(p.read_bytes()).hexdigest())
        html=render(r,root=self.root,frames=[f]);self.assertIn('Sem EV',html);self.assertIn('data:image/png;base64,',html)
        out=self.root/'report.html';write(out,r,root=self.root,frames=[f]);self.assertTrue(out.is_file())
        with self.assertRaises(ValueError):write(out,r)
        with self.assertRaises(ValueError):render(r,root=self.root,frames=[dict(f,sha256='0'*64)])
        with self.assertRaises(ValueError):render(r,root=self.root,frames=[dict(f,file='../frame.png')])
    def test_rebuy_separation(self):
        obs=dict(observed_awards={'SB':0,'BB':2},observed_returns={'SB':0,'BB':1},observed_rake=0,observed_before_rebuy={'SB':199,'BB':201},rebuy={'SB':1,'BB':0},observed_after_rebuy={'SB':200,'BB':201})
        r=declared_settlement({'SB':200,'BB':200},1,2,[dict(position='SB',action='fold',amount=0)],{},rake_bps=0,rake_cap=0,rake_on_fold=False,observations=obs)
        self.assertEqual(r['net_bb']['SB'],-.5);self.assertIn('Liquidação declarada',render(r));self.assertIsNone(r['ev_bb'])

if __name__=='__main__':unittest.main()
