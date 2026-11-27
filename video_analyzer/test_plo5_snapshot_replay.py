import unittest
from plo5_snapshot_replay import positions, chips, replay, from_frame, settlement, SEATS
from plo5_selective_review import select
from plo5_error_prints import capture
from unittest.mock import patch
from pathlib import Path
from tempfile import TemporaryDirectory

H=['As','Ks','Qh','Jd','Tc'];V=['Ah','Kh','Qs','Jc','Td'];B=['2c','3d','4h','5s','6s'];D=['hero_bottom','top']
def seed():return dict(hand_id='h',table_id=1,dealt=D,button='hero_bottom',initial={'hero_bottom':40,'top':40},sb=1,bb=2,pot_includes_pending=True,holding=H)
def snap(t,pot,hero,top,actor,board=(),boundary=False,folded=False):
    return dict(pts=str(t),holding=H,board=list(board),remaining={'hero_bottom':hero,'top':top},pot=pot,actor=actor,folded={'hero_bottom':folded,'top':False},street_boundary=boundary)
def manifest(rows):
    return dict(variant=5,source_sha256='a'*64,frames=[dict(pts=r['pts'],rgb_sha256='b'*64,observations=[dict(table_id=1,field=f,platform='pppoker',layout_candidate_active=True,value_bb=None) for f in ('stack','pot')]) for r in rows])
def run(rows,**kw):return replay(manifest(rows),seed(),rows,**kw)

class SnapshotTests(unittest.TestCase):
    def test_positions_and_exact_units(self):
        self.assertEqual(positions(D,'hero_bottom'),{'top':'BB','hero_bottom':'SB'})
        self.assertEqual(positions(['upper_right','lower_right','hero_bottom','lower_left','upper_left'],'lower_left'),{'upper_left':'SB','upper_right':'BB','lower_right':'UTG','hero_bottom':'CO','lower_left':'BTN'})
        self.assertEqual(chips('4.5',10),45)
        with self.assertRaises(ValueError):chips('4.55',10)
    def test_full_path_and_settlement(self):
        rows=[snap(0,3,39,38,'hero_bottom'),snap(1,4,38,38,'top'),snap(2,4,38,38,None),snap(3,4,38,38,'top',B[:3],True),snap(4,4,38,38,'hero_bottom',B[:3]),snap(5,4,38,38,None,B[:3]),snap(6,4,38,38,'top',B[:4],True),snap(7,4,38,38,'hero_bottom',B[:4]),snap(8,4,38,38,None,B[:4]),snap(9,4,38,38,'top',B,True),snap(10,4,38,38,'hero_bottom',B),snap(11,4,38,38,None,B)]
        r=run(rows);self.assertTrue(r['hand_complete_candidate']);self.assertFalse(r['hands_reconstructed']);self.assertEqual([x['street'] for x in r['decision_records']],['preflop','flop','turn','river'])
        a=select(r['decision_records'],['flop','river']);self.assertEqual(len(a['unresolved']),2);self.assertFalse(a['print_requests'])
        observed=dict(observed_awards={'BB':2,'SB':2},observed_returns={'BB':0,'SB':0},observed_rake=0,observed_before_rebuy={'BB':40,'SB':40},rebuy={'BB':10,'SB':0},observed_after_rebuy={'BB':50,'SB':40})
        s=settlement(seed(),r,{'top':V},observed,rake_bps=0,rake_cap=0,rake_on_fold=False);self.assertEqual(s['status'],'DECLARED_SETTLEMENT_MATCH');self.assertEqual(s['net_bb'],{'BB':'0','SB':'0'});self.assertFalse(s['financial_result_verified'])
        observed['observed_after_rebuy']['BB']=40
        self.assertEqual(settlement(seed(),r,{'top':V},observed,rake_bps=0,rake_cap=0,rake_on_fold=False)['status'],'SETTLEMENT_MISMATCH')
    def test_ambiguity_and_rebuy_no_inference(self):
        a=snap(0,3,39,38,'hero_bottom');b=snap(1,4,38,38,'top');b.pop('actor');b.pop('folded')
        self.assertEqual(run([a,b])['status'],'AMBIGUOUS')
        self.assertEqual(run([a,snap(1,3,40,38,'hero_bottom')])['status'],'PAYOUT_OR_REBUY_UNRESOLVED')
        self.assertEqual(run([a,snap(5,4,38,38,'top')])['status'],'GAP')
    def test_unanchored_street(self):
        a=snap(0,3,39,38,'hero_bottom');b=snap(1,4,38,38,'top',B[:3])
        self.assertEqual(run([a,b])['status'],'UNANCHORED_STREET_TRANSITION');b['street_boundary']=True
        self.assertEqual(run([a,b])['status'],'PRIOR_STREET_NOT_CLOSED')
    def test_frame_adapter(self):
        r=snap(0,3,39,38,'hero_bottom');f=manifest([r])['frames'][0];f['observations'][0]['value_bb']='19.5';f['observations'][1]['value_bb']='1.5'
        f['cards']=[dict(table_id=1,platform='pppoker',hero_cards=H,board_cards=[],seat_evidence=dict(table_id=1,platform='pppoker',dealer={'seat':'hero_bottom'},seats=[dict(seat=s,stack={'candidate':{'hero_bottom':'19.5','top':'19'}.get(s)}) for s in SEATS]))]
        self.assertEqual(from_frame(f,1,D,'hero_bottom',2,actor='hero_bottom')['remaining'],r['remaining'])
        f['cards'][0]['seat_evidence']['seats'][0]['stack']['candidate']=None
        with self.assertRaises(ValueError):from_frame(f,1,D,'hero_bottom',2)
    def test_binding_and_late_action_no_wrong_print(self):
        a=snap(0,3,39,38,'hero_bottom');b=snap(1,4,38,38,None)
        r=run([a,b]);self.assertEqual(len(r['events']),2);self.assertEqual(r['decision_records'][0]['evidence']['pts'],'0')
        m=manifest([a,b]);m['frames'][1]['observations'][0]['platform']=m['frames'][1]['observations'][1]['platform']='suprema'
        self.assertEqual(replay(m,seed(),[a,b])['status'],'PLATFORM_CHANGE')
        # Verify that selection cannot authorize extraction for this replay.
        with TemporaryDirectory() as t:
            p=Path(t)/'v.mp4';p.write_bytes(b'synthetic');import hashlib
            m=manifest([a,b]);m['source_sha256']=hashlib.sha256(p.read_bytes()).hexdigest();r=replay(m,seed(),[a,b])
            with patch('plo5_error_prints.decode') as d:
                out=capture(p,m,r['decision_records'],Path(t)/'out');d.assert_not_called();self.assertEqual(out['unique_crops'],0)
if __name__=='__main__':unittest.main()
