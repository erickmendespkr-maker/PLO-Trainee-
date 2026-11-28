import os
import unittest
from fractions import Fraction
from plo5_terminal_bounds import terminal, prefix, review
from test_plo5_post_gto_river import polar,NUT,BLUFF,CATCH,BOARD
from test_plo5_snapshot_replay import seed
import plo5_pre_gto_tree as pre
import plo5_post_gto_tree as post


def hyp(name,rows):return dict(id=name,provenance='Synthetic decision-time joint prior',deals=[dict(holdings=h,weight=w) for h,w in rows])
def river():return post.step(post.start(polar()),'BB','bet',2)
def model(s,h,rows,**kw):return terminal(s,h,rows,rake_bps=kw.pop('rake_bps',0),rake_cap=kw.pop('rake_cap',0),rake_on_fold=False,**kw)
def interval(r,key):return [Fraction(*x) for x in r['action_ev_bounds_exact'][key]]

class TerminalBoundsTests(unittest.TestCase):
    def test_weighted_exact_and_hypothesis_envelope(self):
        s=river();a=hyp('polar',[({'BB':NUT,'BTN':CATCH},1),({'BB':BLUFF,'BTN':CATCH},2)])
        b=hyp('nuts',[({'BB':NUT,'BTN':CATCH},1)])
        r=model(s,CATCH,[a]);self.assertEqual(interval(r,'call:2'),[2,2]);self.assertEqual(r['conditional_preference'],'CALL');self.assertFalse(r['strategy_verified'])
        r=model(s,CATCH,[a,b]);self.assertEqual(interval(r,'call:2'),[-2,2]);self.assertEqual(r['conditional_preference'],'UNRESOLVED')
        r=model(s,CATCH,[a],rake_bps=5000,rake_cap=2);self.assertEqual(interval(r,'call:2'),[Fraction(2,3)]*2)
    def test_exact_marginal_not_rounded_away(self):
        s=river();a=hyp('marginal',[({'BB':NUT,'BTN':CATCH},133),({'BB':BLUFF,'BTN':CATCH},67)])
        r=model(s,CATCH,[a]);self.assertEqual(interval(r,'call:2'),[Fraction(1,100)]*2);self.assertEqual(r['conditional_preference'],'CALL');self.assertFalse(r['strategy_verified'])
    def test_budget_is_conservative(self):
        s=river();a=hyp('polar',[({'BB':NUT,'BTN':CATCH},1),({'BB':BLUFF,'BTN':CATCH},2)])
        exact=interval(model(s,CATCH,[a]),'call:2')[0];last=None
        for budget in (0,1,2):
            r=model(s,CATCH,[a],max_runouts=budget);lo,hi=interval(r,'call:2');self.assertLessEqual(lo,exact);self.assertGreaterEqual(hi,exact)
            if last:self.assertGreaterEqual(lo,last[0]);self.assertLessEqual(hi,last[1])
            last=(lo,hi)
        self.assertEqual(last,(exact,exact))
    def test_preflop_and_sidepot_bounds(self):
        s=pre.start({'BTN':7,'SB':4,'BB':10},1,2);s=pre.step(s,'BTN','raise',7);s=pre.step(s,'SB','call',3)
        h=hyp('three',[({'BTN':NUT,'SB':BLUFF,'BB':CATCH},1)])
        r=model(s,CATCH,[h],max_runouts=0);self.assertEqual(interval(r,'call:5'),[Fraction(-5,2),Fraction(13,2)]);self.assertEqual(r['hypotheses'][0]['total_runouts'],435897)
        a=model(s,CATCH,[h],max_runouts=8);self.assertEqual(a['hypotheses'][0]['evaluated_runouts'],8);self.assertFalse(a['hypotheses'][0]['exact']);self.assertLessEqual(interval(a,'call:5')[1],Fraction(13,2))
    def test_river_sidepot_and_native_parity(self):
        s=pre.start({'BTN':7,'SB':4,'BB':10},1,2)
        for p,a,v in [('BTN','call',2),('SB','call',1),('BB','check',0)]:s=pre.step(s,p,a,v)
        from plo5_snapshot_replay import reveal
        s=reveal(s,BOARD[:3])
        for c in BOARD[3:]:
            for p in s.order:s=post.step(s,p,'check',0)
            s=reveal(s,[c])
        s=post.step(s,'SB','bet',2);s=post.step(s,'BB','raise',5)
        h=hyp('side',[({'SB':NUT,'BB':BLUFF,'BTN':CATCH},1)])
        r=model(s,CATCH,[h]);self.assertEqual(interval(r,'call:5'),[Fraction(1,2)]*2)
        exe=os.environ.get('PLO5_RANK_WORKER_EXE')
        if exe:
            from plo5_rank_worker import RankWorker
            with RankWorker(exe) as w:a=model(s,CATCH,[h],rank_worker=w)
            self.assertEqual(dict(a,rank_backend='python'),r)
    def test_reject_conflicts_and_nonterminal(self):
        s=river();a=hyp('bad',[({'BB':CATCH,'BTN':CATCH},1)])
        with self.assertRaises(ValueError):model(s,CATCH,[a])
        s=pre.start({'SB':100,'BB':100},1,2);self.assertEqual(model(s,CATCH,[a])['status'],'NONTERMINAL_OR_OTHER_LEGAL_ACTIONS')
    def test_prefix_isolation_and_candidate_review(self):
        sd=seed();events=[dict(position='SB',action='call',amount=1),dict(position='BB',action='check',amount=0),dict(cards=['2c','3d','4h'])]
        d=dict(hand_id='h',decision_id='0',street='preflop',action='call:1',reconstruction_verified=False,strategy_verified=False,action_ev_bounds={})
        r=dict(version='plo5-auto-reconstruction-candidates-v1',hands_reconstructed=False,strategy_authorized=False,hands=[dict(seed=sd,events=events)],decision_records=[d]);a=review(r,{});events[2]={'cards':['2s','3s','4s']};self.assertEqual(a,review(r,{}));self.assertEqual(a['estimates'][0]['status'],'NO_DECLARED_DECISION_RANGES');self.assertEqual(len(a['selection']['unresolved']),1);self.assertFalse(a['selection']['print_requests']);self.assertEqual(review(r,{},['river'])['estimates'],[])
        d['action']='raise:2'
        with self.assertRaises(ValueError):review(r,{})

if __name__=='__main__':unittest.main()
