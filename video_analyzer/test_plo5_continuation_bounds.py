import os
import unittest
from fractions import Fraction
from plo5_continuation_bounds import digest, prior_at_decision, evaluate_decision, envelopes, review
from plo5_snapshot_replay import reveal
from test_plo5_post_gto_river import NUT, BLUFF, CATCH, BOARD, context
import plo5_pre_gto_tree as pre
import plo5_post_gto_tree as post


def seed():
    return dict(hand_id='h',table_id=1,dealt=['top','hero_bottom'],button='hero_bottom',initial={'top':8,'hero_bottom':8},sb=1,bb=2,pot_includes_pending=True,holding=CATCH)


def action(p,a,n=0):return dict(position=p,action=a,amount=n)


def config(sd,events,j):
    src=dict(description='Synthetic explicit action likelihoods',source_sha256=digest('synthetic'))
    es=[e for e in events[:j] if e.get('position')=='BB']
    return dict(prefix_sha256=digest(dict(seed=sd,events=events[:j])),rake_bps=0,rake_cap=0,rake_on_fold=False,hypotheses=[dict(id='p',provenance=src,deals=[dict(holdings={'SB':CATCH,'BB':h},weight=1,likelihoods=[dict(event=e,probability=p) for e in es]) for h,p in [(NUT,[1,4]),(BLUFF,[3,4])]])])


class ContinuationTests(unittest.TestCase):
    def test_river_nonterminal_all_sizings_and_oracle(self):
        s=post.start(context([(NUT,1)],[(CATCH,1)],stacks=(3,3),pot=2,bb=1));deal=[((tuple(sorted(NUT)),tuple(sorted(CATCH))),Fraction(1))]
        acts=[('check',0),('bet',1),('bet',2)]
        r,stats=envelopes(s,'BB',deal,acts,rake_bps=0,rake_cap=0,rake_on_fold=False,max_nodes=1000)
        # Even a player with the nuts may fold after a raise; these bounds include that.
        self.assertEqual(r,{'check:0':(-2,5),'bet:1':(-1,5),'bet:2':(-2,5)})
        self.assertTrue(all(x['cutoffs']==0 for x in stats.values()))
        small,_=envelopes(s,'BB',deal,acts,rake_bps=0,rake_cap=0,rake_on_fold=False,max_nodes=1)
        for k in r:self.assertLessEqual(small[k][0],r[k][0]);self.assertGreaterEqual(small[k][1],r[k][1])
    def test_terminal_marginal_and_native_parity(self):
        s=post.step(post.start(context([(NUT,133),(BLUFF,67)],[(CATCH,1)])),'BB','bet',2)
        deals=[((tuple(sorted(h)),tuple(sorted(CATCH))),Fraction(w,200)) for h,w in [(NUT,133),(BLUFF,67)]]
        args=dict(rake_bps=0,rake_cap=0,rake_on_fold=False,max_nodes=100)
        r,stats=envelopes(s,'BTN',deals,[('fold',0),('call',2)],**args);self.assertEqual(r['call:2'],(Fraction(1,100),)*2)
        exe=os.environ.get('PLO5_RANK_WORKER_EXE')
        if exe:
            from plo5_rank_worker import RankWorker
            from plo5_rank_lru import CachedRankWorker
            with RankWorker(exe) as w:self.assertEqual(envelopes(s,'BTN',deals,[('fold',0),('call',2)],rank_worker=CachedRankWorker(w),**args),(r,stats))
    def test_posterior_and_future_isolation(self):
        sd=seed();events=[action('SB','call',1),action('BB','check'),dict(cards=BOARD[:3]),action('BB','check'),action('SB','check'),dict(cards=[BOARD[3]])]
        cfg=config(sd,events,4);s,h,a,ps,key=prior_at_decision(sd,events,4,cfg);self.assertEqual(sorted(w for _,w in ps[0][2]),[Fraction(1,10),Fraction(9,10)])
        r=evaluate_decision(sd,events,4,cfg,max_nodes=16);events[-1]={'cards':['Ac']};self.assertEqual(r,evaluate_decision(sd,events,4,cfg,max_nodes=16));self.assertFalse(r['strategy_verified']);self.assertTrue(r['action_set_complete'])
        cfg['prefix_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'prefix mismatch'):prior_at_decision(sd,events,4,cfg)
    def test_blocker_elimination_and_wrong_likelihood(self):
        sd=seed();events=[action('SB','call',1),action('BB','check'),dict(cards=['As','3d','4h']),action('BB','check'),action('SB','check')]
        cfg=config(sd,events,4);self.assertEqual(len(prior_at_decision(sd,events,4,cfg)[3][0][2]),1)
        cfg['hypotheses'][0]['deals'][1]['likelihoods'][0]['event']=action('BB','raise',2)
        with self.assertRaisesRegex(ValueError,'event mismatch'):prior_at_decision(sd,events,4,cfg)
    def test_preflop_budget_and_incomplete_action_set(self):
        sd=seed();sd['initial']={'top':200,'hero_bottom':200};events=[action('SB','raise',5)];cfg=config(sd,events,0);r=evaluate_decision(sd,events,0,cfg,max_nodes=8);self.assertIn('raise:5',r['action_ev_bounds_exact']);self.assertTrue(r['action_set_complete']);self.assertTrue(any(q['cutoffs'] for q in r['hypotheses'][0]['stats'].values()))
        sd['button']='top';events=[action('SB','raise',5),action('BB','raise',16),action('SB','raise',44),action('BB','raise',100)];cfg=config(sd,events,3)
        for d in cfg['hypotheses'][0]['deals']:
            d['holdings']['SB'],d['holdings']['BB']=d['holdings']['BB'],d['holdings']['SB'];d['likelihoods']=[dict(event=e,probability=[1,1]) for e in events[:3] if e['position']=='SB']
        r=evaluate_decision(sd,events,3,cfg,max_nodes=8);self.assertFalse(r['action_set_complete']);self.assertEqual(r['legal_action_count'],71);self.assertIn('raise:100',r['action_ev_bounds_exact'])
    def test_multiway_sidepot(self):
        s=pre.start({'BTN':7,'SB':4,'BB':10},1,2)
        for p,a,v in [('BTN','call',2),('SB','call',1),('BB','check',0)]:s=pre.step(s,p,a,v)
        s=reveal(s,BOARD[:3])
        for c in BOARD[3:]:
            for p in s.order:s=post.step(s,p,'check',0)
            s=reveal(s,[c])
        s=post.step(s,'SB','bet',2);s=post.step(s,'BB','raise',5);deal=[((tuple(sorted(NUT)),tuple(sorted(BLUFF)),tuple(sorted(CATCH))),Fraction(1))]
        r,_=envelopes(s,'BTN',deal,[('fold',0),('call',5)],rake_bps=0,rake_cap=0,rake_on_fold=False,max_nodes=100);self.assertEqual(r['call:5'],(Fraction(1,2),)*2)
    def test_turn_chance_with_blockers(self):
        from plo5_post_gto_context import DECK
        from plo5_evaluator import evaluate
        s=post.step(post.start(context([(NUT,1)],[(CATCH,1)],board=BOARD[:4])),'BB','bet',2)
        deal=[((tuple(sorted(NUT)),tuple(sorted(CATCH))),Fraction(1))];a=dict(rake_bps=0,rake_cap=0,rake_on_fold=False)
        deck=sorted(DECK-set(NUT+CATCH+BOARD[:4]));expected=Fraction(0)
        for c in deck:
            x,y=[evaluate(h,BOARD[:4]+[c])['rank'] for h in (NUT,CATCH)];expected+=6*(Fraction(1) if y>x else Fraction(1,2) if y==x else 0)-2
        expected/=len(deck);r,_=envelopes(s,'BTN',deal,[('call',2)],max_nodes=100,**a);self.assertEqual(r['call:2'],(expected,expected));self.assertEqual(len(deck),38)
        low,_=envelopes(s,'BTN',deal,[('call',2)],max_nodes=4,**a);self.assertLessEqual(low['call:2'][0],expected);self.assertGreaterEqual(low['call:2'][1],expected)
    def test_candidate_review_never_promotes(self):
        sd=seed();events=[action('SB','call',1)];d=dict(hand_id='h',decision_id='0',street='preflop',action='call:1',reconstruction_verified=False,strategy_verified=False,action_set_complete=False,action_ev_bounds={});r=dict(version='plo5-auto-reconstruction-candidates-v1',hands_reconstructed=False,strategy_authorized=False,hands=[dict(seed=sd,events=events)],decision_records=[d]);a=review(r,{});self.assertEqual(a['estimates'][0]['status'],'NO_DECLARED_CONTINUATION_PRIOR');a=review(r,{'h':{'0':config(sd,events,0)}},max_nodes=8);self.assertFalse(a['strategy_verified']);self.assertEqual(len(a['selection']['unresolved']),1);self.assertFalse(a['selection']['print_requests'])

if __name__=='__main__':unittest.main()
