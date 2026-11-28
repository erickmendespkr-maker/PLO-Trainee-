import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from plo5_auto_reconstruct import ReconstructionStream, reconstruct, SEATS, BACK, EMPTY
from plo5_integrated_video import run
from plo5_acceptance import audit
from test_plo5_snapshot_replay import H,B

BANK=Path(__file__).resolve().parents[1]/'calibration'/'ppp_bank.json'


def frame(t,pot,hero,top,*,board=(),actor=None,labels=None,holding=H):
    labels=labels or {};values={'hero_bottom':str(hero/10),'top':str(top/10)}
    return dict(pts=str(t),rgb_sha256='a'*64,observations=[dict(table_id=1,field=f,platform='pppoker',layout_candidate_active=True,value_bb=values['hero_bottom'] if f=='stack' else None if pot is None else str(pot/10)) for f in ('stack','pot')],cards=[dict(table_id=1,platform='pppoker',rank_profile='test',hero_cards=holding,board_cards=list(board),actor_candidate=actor,seat_evidence=dict(table_id=1,platform='pppoker',dealer={'seat':'hero_bottom'},seats=[dict(seat=s,stack={'candidate':values.get(s)},action={'candidate':labels.get(s)}) for s in SEATS]),opponent_evidence=dict(table_id=1,platform='pppoker',opponents=[dict(seat=s,status=BACK if s=='top' else EMPTY) for s in SEATS if s!='hero_bottom']))])


def manifest(frames,source='b'*64):return dict(variant=5,source_sha256=source,frames=frames)


def full_hand():
    a=[frame(0,15,195,190,actor='hero_bottom'),frame(1,20,190,190,labels={'hero_bottom':'call','top':'check'}),frame(2,20,190,190,labels={'hero_bottom':'call','top':'check'})]
    for j,n in enumerate((3,4,5)):
        t=3+3*j;a.extend([frame(t,20,190,190,board=B[:n]),frame(t+1,20,190,190,board=B[:n],actor='hero_bottom',labels={'top':'check'}),frame(t+2,20,190,190,board=B[:n],labels={'hero_bottom':'check'})])
    return a


def collect(parts):
    s=ReconstructionStream(1);hands=[];records=[];anchors={}
    for i,p in enumerate(parts):
        r=s.feed(manifest(p),final=i==len(parts)-1);hands.extend(r['hands']);records.extend(r['decision_records']);anchors.update({f['pts']:f for f in r['anchor_frames']})
    return hands,records,anchors,dict(s.counts)


class ContinuityTests(unittest.TestCase):
    def test_all_splits_equal_unsplit(self):
        rows=full_hand();ref=collect([rows]);self.assertEqual(len(ref[0]),1);self.assertEqual([d['street'] for d in ref[1]],['preflop','flop','turn','river']);self.assertEqual(ref[0][0]['end_reason'],'TERMINAL_CANDIDATE')
        for k in range(1,len(rows)):self.assertEqual(collect([rows[:k],rows[k:]]),ref)
        self.assertEqual(collect([[f] for f in rows]),ref);self.assertEqual(len({(d['hand_id'],d['decision_id']) for d in ref[1]}),4);self.assertEqual(set(ref[2]),{'0','4','7','10'})
    def test_deferred_partial_cross_boundary(self):
        rows=[frame(0,15,195,190,actor='hero_bottom'),frame(1,None,190,190,holding=None),frame(2,20,190,190,labels={'hero_bottom':'call','top':'check'})]
        a=collect([rows]);b=collect([rows[:2],rows[2:]]);self.assertEqual(a,b);self.assertEqual(a[0][0]['events'],[dict(position='SB',action='call',amount=5),dict(position='BB',action='check',amount=0)]);self.assertEqual(a[0][0]['intervals'][-1]['checkpoint_pts'],['1']);self.assertIn('0',a[2]);self.assertEqual(a[3]['DEFERRED_PARTIAL'],1)
    def test_no_early_or_duplicate_emission(self):
        rows=full_hand();s=ReconstructionStream(1);a=s.feed(manifest(rows[:2]));self.assertTrue(a['active_hand']);self.assertFalse(a['decision_records']);b=s.feed(manifest(rows[2:]),final=True);self.assertFalse(b['active_hand']);self.assertEqual(len(b['decision_records']),4);self.assertEqual(len(b['hands']),1)
        with self.assertRaises(ValueError):s.feed(manifest([]))
    def test_reject_source_overlap_and_missing_table(self):
        rows=full_hand();s=ReconstructionStream(1);s.feed(manifest(rows[:1]))
        for m in (manifest(rows[:2]),manifest(rows[1:2],'c'*64),manifest([dict(rows[1],cards=[])])):
            with self.assertRaises(ValueError):s.feed(m)
        self.assertEqual(s.feed(manifest(rows[1:]),final=True)['hands'],collect([rows])[0])
    def test_gap_and_payout_still_close(self):
        a=frame(0,15,195,190,actor='hero_bottom');b=frame(3,20,190,190,labels={'hero_bottom':'call'});r=collect([[a],[b]]);self.assertEqual(r[0][0]['end_reason'],'CONTINUITY_UNKNOWN');self.assertFalse(r[1])
        b=frame(1,15,205,190);r=collect([[a],[b]]);self.assertEqual(r[0][0]['end_reason'],'PAYOUT_OR_REBUY_UNRESOLVED');self.assertFalse(r[1])
    def test_bounded_active_hand_and_repeat_seed(self):
        rows=[frame(t,15,195,190,actor='hero_bottom') for t in range(2051)];r=collect([rows[i:i+100] for i in range(0,len(rows),100)]);self.assertEqual(len(r[0]),1);self.assertEqual(r[0][0]['end_reason'],'ACTIVE_HAND_BUDGET');self.assertEqual(len(r[0][0]['intervals']),2048);self.assertFalse(r[1]);self.assertGreater(r[3]['REPEATED_SEED_SKIPPED'],0)


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe') and BANK.exists(),'FFmpeg and bank required')
class CrossWindowReportTests(unittest.TestCase):
    def test_report_anchor_from_prior_window_and_audit(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp);v=p/'v.mp4';subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=black:s=1504x696:r=4','-t','4','-c:v','libx264','-threads','1','-pix_fmt','yuv420p',str(v)],check=True,timeout=30)
            rows=full_hand()[:4]
            def observe(source,coarse,refined,tables,money,card,seat,dealt,**kw):
                return dict(variant=5,source_sha256=coarse['source_sha256'],actions_verified=False,strategy_authorized=False,frames=[dict(rows[int(f['pts'])],rgb_sha256=f['rgb_sha256'],file=f['file']) for f in coarse['frames']])
            out=p/'out'
            with patch('plo5_integrated_video.observe_shared',side_effect=observe):r=run(v,out,ppp=BANK,tables=[1],chunk=2,workers=1,refine_budget=0)
            self.assertFalse(r['window_boundaries_split_hands']);self.assertEqual([w['candidate_decisions'] for w in r['windows']],[0,1]);self.assertEqual(r['counts']['prints'],0);self.assertEqual(audit(v,out)['metric_records_replayed'],1)
            q=out/'window_00002/candidates.json';data=json.loads(q.read_text());self.assertEqual([x['pts'] for x in data['carried_anchors']],['0']);data['carried_anchors'][0]['rgb_sha256']='0'*64;q.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,'Carried anchor mismatch'):audit(v,out)

if __name__=='__main__':unittest.main()
