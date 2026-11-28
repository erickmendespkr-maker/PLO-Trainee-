import unittest
from copy import deepcopy
from plo5_auto_reconstruct import BACK,EMPTY,recover,reconstruct,seed_from,snapshot,SEATS,hero_turn,observe
import plo5_pre_gto_tree as pre

H=['As','Ks','Qh','Jd','Tc']

def frame(t,hero,bb,pot,labels=None,back=BACK,board=None):
    labels=labels or {};st={'hero_bottom':str(hero),'top':str(bb)}
    seats=[dict(seat=k,stack=dict(candidate=st.get(k)),action=dict(candidate=labels.get(k))) for k in SEATS]
    opponents=[dict(seat=k,status=back if k=='top' else EMPTY) for k in SEATS if k!='hero_bottom']
    c=dict(table_id=1,platform='pppoker',rank_profile='test',hero_cards=H,board_cards=[] if board is None else board,seat_evidence=dict(table_id=1,platform='pppoker',dealer=dict(seat='hero_bottom'),seats=seats),opponent_evidence=dict(table_id=1,platform='pppoker',opponents=opponents))
    return dict(pts=str(t),rgb_sha256='a'*64,observations=[dict(table_id=1,platform='pppoker',layout_candidate_active=True,field=k,value_bb=str(v)) for k,v in [('stack',hero),('pot',pot)]],cards=[c])

def manifest(*frames):return dict(variant=5,source_sha256='b'*64,frames=list(frames))

class AutoTests(unittest.TestCase):
    def test_seed_requires_positive_roster_evidence(self):
        f=frame(0,9.5,9,1.5);s=snapshot(f,1,10);d=seed_from(s,1,5,10);self.assertEqual(d['initial'],{'top':100,'hero_bottom':100})
        s['opponents']['upper_right']='unknown'
        with self.assertRaisesRegex(ValueError,'Unresolved dealt roster'):seed_from(s,1,5,10)
    def test_raise_fold_and_persistent_label(self):
        a=frame(0,9.5,9,1.5);b=frame(1,7,9,4,{'hero_bottom':'raise'});c=frame(2,7,9,4,{'hero_bottom':'raise','top':'fold'},'unknown')
        r=reconstruct(manifest(a,b,c),1);self.assertEqual(r['hands'][0]['events'],[dict(position='SB',action='raise',amount=25),dict(position='BB',action='fold',amount=0)]);self.assertEqual(r['hands'][0]['end_reason'],'TERMINAL_CANDIDATE');self.assertEqual(len(r['decision_records']),1);self.assertFalse(r['strategy_authorized']);self.assertFalse(r['selection']['print_requests']);self.assertEqual(r['selection']['unresolved'][0]['street'],'preflop')
    def test_ambiguous_zero_cost_and_budget(self):
        s=pre.start({'SB':100,'BB':100},5,10);r=recover(s,{'SB':90,'BB':90},20,active=['BB'],labels={'SB':'call'});self.assertEqual(r['status'],'AMBIGUOUS');self.assertEqual(recover(s,{'SB':90,'BB':90},20,max_nodes=1)['status'],'SEARCH_BUDGET_EXCEEDED')
    def test_payout_and_nonconservation(self):
        s=pre.start({'SB':100,'BB':100},5,10);self.assertEqual(recover(s,{'SB':100,'BB':90},10)['status'],'PAYOUT_OR_REBUY_UNRESOLVED');self.assertEqual(recover(s,{'SB':90,'BB':90},15)['status'],'DISPLAY_NOT_CONSERVED')
    def test_gap_and_duplicate_seed(self):
        r=reconstruct(manifest(frame(0,9.5,9,1.5),frame(4,9.5,9,1.5)),1);self.assertEqual(len(r['hands']),1);self.assertEqual(r['hands'][0]['end_reason'],'CONTINUITY_UNKNOWN');self.assertEqual(r['counts']['REPEATED_SEED_SKIPPED'],1)
    def test_invalid_dealt_stack_and_conflict(self):
        a=frame(0,9.5,9,1.5);b=deepcopy(a);b['pts']='1';b['cards'][0]['seat_evidence']['seats'][0]['stack']['candidate']=None
        r=reconstruct(manifest(a,b),1);self.assertEqual(r['hands'][0]['unresolved_checkpoint_pts'],['1']);self.assertFalse(r['hands'][0]['events'])

    def test_actor_marker_and_partial_checkpoint(self):
        from PIL import Image,ImageDraw
        im=Image.new('RGB',(1504,696));d=ImageDraw.Draw(im)
        for x,color in [(17,(170,50,50)),(142,(30,150,60)),(264,(180,160,30))]:d.rectangle((x,657,x+7,662),fill=color)
        self.assertEqual(hero_turn(im,1,'pppoker'),'hero_bottom');self.assertIsNone(hero_turn(im,2,'pppoker'));self.assertIsNone(hero_turn(im,1,'suprema'))
        a=frame(0,9.5,9,1.5);b=frame('1/2',9.5,9,1.5);b['cards'][0]['hero_cards']=None
        c=frame(1,7,9,4,{'hero_bottom':'raise'});r=reconstruct(manifest(a,b,c),1)
        self.assertEqual(r['counts']['DEFERRED_PARTIAL'],1);self.assertEqual(r['hands'][0]['events'][0]['amount'],25);self.assertEqual(r['hands'][0]['intervals'][-1]['checkpoint_pts'],['1/2'])
        b['observations'][1]['value_bb']='99';r=reconstruct(manifest(a,b,c),1);self.assertEqual(r['hands'][0]['end_reason'],'NO_MATCH_WITHIN_BOUNDS');self.assertFalse(r['decision_records'])
    def test_actor_condition_disambiguates_call(self):
        s=pre.start({'SB':100,'BB':100},5,10)
        a=recover(s,{'SB':90,'BB':90},20,active=['BB'],expected_actor='BB');self.assertEqual(a['status'],'UNIQUE_WITHIN_BOUNDS');self.assertEqual(a['paths'][0],[dict(position='SB',action='call',amount=5)])
    def test_source_and_refinement_identity(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from hashlib import sha256
        from unittest.mock import patch
        with TemporaryDirectory() as t:
            p=Path(t)/'v.mp4';p.write_bytes(b'fixture');m=manifest(frame(0,9.5,9,1.5));m['source_sha256']=sha256(b'fixture').hexdigest()
            r=dict(variant=5,version='plo5-card-refinement-v1',source_sha256=m['source_sha256'],frames=[dict(pts='0',rgb_sha256='a'*64,target_tables=[1])])
            with patch('plo5_auto_reconstruct.decode') as decoder:
                with self.assertRaisesRegex(ValueError,'Duplicate refinement'):observe(p,m,r,1,None,None,None,None)
                decoder.assert_not_called()
            m['source_sha256']='0'*64
            with self.assertRaisesRegex(ValueError,'Source mismatch'):observe(p,m,None,1,None,None,None,None)

    def test_dealer_dropout_deferred_and_reanchored(self):
        a=frame(0,9.5,9,1.5);b=frame('1/2',9.5,9,1.5)
        b['cards'][0]['seat_evidence']['dealer']['seat']=None
        c=frame(1,7,9,4,{'hero_bottom':'raise'})
        r=reconstruct(manifest(a,b,c),1)
        self.assertEqual(r['counts']['DEFERRED_DEALER_MISSING'],1)
        self.assertEqual(r['hands'][0]['events'][0]['amount'],25)
        self.assertEqual(r['hands'][0]['intervals'][-1]['checkpoint_pts'],['1/2'])
        self.assertFalse(r['hands'][0]['hand_verified'])
        c['cards'][0]['seat_evidence']['dealer']['seat']='top'
        r=reconstruct(manifest(a,b,c),1)
        self.assertEqual(r['counts']['CONTINUITY_DEALER_CONFLICT'],1)
        self.assertEqual(r['hands'][0]['end_reason'],'CONTINUITY_UNKNOWN')
        self.assertFalse(r['decision_records'])

    def test_partial_chain_stays_contiguous_without_losing_anchor(self):
        a=frame(0,9.5,9,1.5);b=frame(1,9.5,9,1.5);c=frame(2,9.5,9,1.5)
        for item in (b,c):
            item['cards'][0]['seat_evidence']['dealer']['seat']=None
            item['cards'][0]['hero_cards']=None
        d=frame(3,7,9,4,{'hero_bottom':'raise'})
        r=reconstruct(manifest(a,b,c,d),1)
        self.assertEqual(r['counts'].get('CONTINUITY_PTS_GAP',0),0)
        self.assertEqual(r['counts']['DEFERRED_PARTIAL'],2)
        self.assertEqual(r['hands'][0]['events'][0],dict(position='SB',action='raise',amount=25))
        self.assertEqual(r['hands'][0]['intervals'][-1]['checkpoint_pts'],['1'])
        self.assertEqual(r['counts']['DEFERRED_DUPLICATE'],1)
        d['cards'][0]['seat_evidence']['dealer']['seat']='top'
        r=reconstruct(manifest(a,b,c,d),1)
        self.assertEqual(r['counts']['CONTINUITY_DEALER_CONFLICT'],1)
        self.assertFalse(r['decision_records'])

    def test_dealer_dropout_cannot_bridge_gap_or_advance_street(self):
        a=frame(0,9.5,9,1.5);b=frame(1,9.5,9,1.5)
        b['cards'][0]['seat_evidence']['dealer']['seat']=None
        c=frame(4,7,9,4,{'hero_bottom':'raise'})
        r=reconstruct(manifest(a,b,c),1)
        self.assertEqual(r['counts']['CONTINUITY_PTS_GAP'],1)
        self.assertFalse(r['decision_records'])
        r=reconstruct(manifest(a,b),1)
        self.assertEqual(r['hands'][0]['unresolved_checkpoint_pts'],['1'])
        self.assertFalse(r['decision_records'])


    def test_many_identical_partial_frames_compact_and_resume(self):
        from fractions import Fraction
        a=frame(0,9.5,9,1.5)
        repeats=[frame(Fraction(i,10),9.5,9,1.5) for i in range(1,12)]
        for f in repeats:
            f['cards'][0]['hero_cards']=None
            f['cards'][0]['seat_evidence']['dealer']['seat']=None
        z=frame('3/2',7,9,4,{'hero_bottom':'raise'})
        r=reconstruct(manifest(a,*repeats,z),1)
        self.assertEqual(r['counts']['DEFERRED_PARTIAL'],11)
        self.assertEqual(r['counts']['DEFERRED_DUPLICATE'],10)
        self.assertEqual(len(r['hands']),1)
        self.assertEqual(r['hands'][0]['events'][0]['amount'],25)
        self.assertEqual(r['hands'][0]['replay_audit']['status'],'LEGAL_PREFIX_CONSISTENT')

    def test_stable_complete_ambiguity_does_not_timeout_at_three_seconds(self):
        a=frame(0,9.5,9,1.5)
        stable=[frame(i,9,9,2) for i in range(1,11)]
        r=reconstruct(manifest(a,*stable),1)
        self.assertEqual(r['hands'][0]['end_reason'],'WINDOW_END')
        self.assertEqual(r['counts']['DEFERRED_AMBIGUOUS'],10)
        self.assertEqual(r['counts']['DEFERRED_DUPLICATE'],9)
        self.assertEqual(r['hands'][0]['unresolved_checkpoint_pts'],['1'])
        self.assertFalse(r['decision_records'])

    def test_complete_ambiguity_still_has_absolute_time_bound(self):
        a=frame(0,9.5,9,1.5)
        stable=[frame(i,9,9,2) for i in range(1,23)]
        r=reconstruct(manifest(a,*stable),1)
        self.assertEqual(r['hands'][0]['end_reason'],'CHECKPOINT_TIMEOUT')
        self.assertFalse(r['decision_records'])

    def test_partial_evidence_cannot_span_unbounded_time(self):
        a=frame(0,9.5,9,1.5)
        repeats=[frame(i,9.5,9,1.5) for i in range(1,7)]
        for f in repeats:
            f['cards'][0]['hero_cards']=None
            f['cards'][0]['seat_evidence']['dealer']['seat']=None
        r=reconstruct(manifest(a,*repeats),1)
        self.assertEqual(r['hands'][0]['end_reason'],'CHECKPOINT_TIMEOUT')
        self.assertFalse(r['decision_records'])

    def test_replay_divergence_suppresses_candidate_decisions(self):
        from unittest.mock import patch
        a=frame(0,9.5,9,1.5)
        b=frame(1,7,9,4,{'hero_bottom':'raise'})
        c=frame(2,7,9,4,{'hero_bottom':'raise','top':'fold'},'unknown')
        with patch('plo5_auto_reconstruct.audit_auto_events',return_value={'status':'TERMINAL_MISMATCH'}):
            r=reconstruct(manifest(a,b,c),1)
        self.assertEqual(r['counts']['REPLAY_AUDIT_REJECTED'],1)
        self.assertFalse(r['decision_records'])
        self.assertEqual(r['hands'][0]['replay_audit']['status'],'TERMINAL_MISMATCH')

    def test_unique_prior_street_close_recovers_board_transition_without_strategy_certification(self):
        # Two-player preflop: SB calls the remaining blind, BB checks;
        # both actions may be hidden between consecutive sampled screens.
        initial=frame(0,9.5,9,1.5)
        flop=frame(1,9,9,2,board=['2c','3d','4h'])
        r=reconstruct(manifest(initial,flop),1)
        self.assertEqual(len(r['hands']),1)
        self.assertEqual(r['hands'][0]['events'],[
            dict(position='SB',action='call',amount=5),
            dict(position='BB',action='check',amount=0),
            dict(cards=['2c','3d','4h'])])
        self.assertEqual(r['counts']['BOUNDARY_UNIQUE_WITHIN_BOUNDS'],1)
        self.assertEqual(r['counts']['BOUNDARY_ACTIONS_UNVERIFIED'],2)
        self.assertEqual(r['hands'][0]['replay_audit']['status'],'LEGAL_PREFIX_CONSISTENT')
        self.assertFalse(r['decision_records'])
        self.assertFalse(r['hands'][0]['hand_verified'])
        self.assertFalse(r['financial_result_verified'])

    def test_boundary_without_conserving_pot_never_invents_prior_actions(self):
        initial=frame(0,9.5,9,1.5)
        impossible=frame(1,9,9,2.5,board=['2c','3d','4h'])
        r=reconstruct(manifest(initial,impossible),1)
        self.assertEqual(r['hands'][0]['end_reason'],'UNANCHORED_STREET')
        self.assertFalse(r['hands'][0]['events'])
        self.assertFalse(r['decision_records'])

    def test_ambiguous_street_close_never_invents_actions(self):
        initial=frame(0,9.5,9,1.5)
        # Flop observed while the displayed pot and both stacks remain
        # unchanged; BB and SB have not legally completed preflop.
        premature=frame(1,9.5,9,1.5,board=['2c','3d','4h'])
        r=reconstruct(manifest(initial,premature),1)
        self.assertEqual(r['hands'][0]['end_reason'],'UNANCHORED_STREET')
        self.assertFalse(r['decision_records'])

if __name__=='__main__':unittest.main()
