import copy
import unittest
from plo5_window_review import build, FLAGS

H='As Kd Qh Jc Ts'.split(); B='2c 3d 4h'.split()

def window(n,start,boards,heroes=None,visible=None,tables=(1,)):
    rows=[]
    for tid in tables:
        for i,b in enumerate(boards):
            rows.append(dict(file=f'table_{tid:02d}_{i+1:03d}.png',table_id=tid,pts=start+i+.1,sha256='d'*64,visible=True if visible is None else visible[i],hero_cards=H if heroes is None else heroes[i],board_cards=b,action_reading=None))
    return dict(window=f'window_{n:02d}',money=None,timeline=dict(variant=5,job_id='a'*32,source_sha256='b'*64,sparse_manifest_sha256='c'*64,annotation_sha256='e'*64,start=start,seconds=len(boards),observations=rows,**{k:False for k in FLAGS}))

class ReviewTests(unittest.TestCase):
    def test_contiguous(self):
        r=build([window(2,2,[B,B+['5c']]),window(1,0,[[],[]])]);s=r['segments'][0]
        self.assertEqual(len(r['segments']),1);self.assertEqual(len(s['frames']),4);self.assertEqual(s['windows'],['window_01','window_02']);self.assertEqual(s['corroborated_hero_candidates'][0]['observations'],4);self.assertFalse(r['hands_reconstructed'])
    def test_reset(self):
        r=build([window(1,0,[B,B]),window(2,2,[[],[]])]);self.assertEqual(len(r['segments']),2);self.assertEqual(r['segments'][1]['start_reason'],'board_reset_or_conflict')
    def test_gap(self):
        r=build([window(1,0,[[],[]]),window(2,3,[B,B])]);self.assertEqual(r['segments'][1]['start_reason'],'sampling_gap')
    def test_visibility(self):
        r=build([window(1,0,[[],[],B],visible=[True,None,True])]);self.assertEqual(len(r['unassigned']),1);self.assertEqual(len(r['segments']),2)
    def test_tables(self):
        r=build([window(1,0,[[],[]],tables=(1,2,3,4)),window(2,2,[B,B],tables=(1,2,3,4))]);self.assertEqual(len(r['segments']),4);self.assertEqual(r['observations'],16)
    def test_overlap(self):
        with self.assertRaisesRegex(ValueError,'Overlapping'):build([window(1,0,[[],[]]),window(2,1,[B,B])])
    def test_identity(self):
        w=window(2,2,[B,B]);w['timeline']['source_sha256']='f'*64
        with self.assertRaisesRegex(ValueError,'Mixed'):build([window(1,0,[[],[]]),w])
    def test_cross_frame(self):
        r=build([window(1,0,[[],['As','2c','3d']],heroes=[H,None])]);self.assertEqual(r['unassigned'][0]['reason'],'cross_frame_card_conflict')
    def test_money(self):
        w=window(1,0,[[],B]);t=w['timeline'];w['money']=dict(variant=5,job_id=t['job_id'],source_sha256=t['source_sha256'],financial_result_verified=False,observations=[dict(file=r['file'],table_id=r['table_id'],pts=r['pts'],crop_sha256=r['sha256'],stack_bb='100' if i==0 else '60',pot_bb='40') for i,r in enumerate(t['observations'])]);s=build([w])['segments'][0];self.assertEqual(s['stack_observations'],2);self.assertIsNone(s['financial_result_bb']);w['money']['observations'][0]['crop_sha256']='f'*64
        with self.assertRaisesRegex(ValueError,'Money crop mismatch'):build([w])
    def test_incomplete(self):
        w=window(1,0,[[],[]]);w['timeline']['observations'].pop()
        with self.assertRaisesRegex(ValueError,'Incomplete'):build([w])
    def test_roster(self):
        with self.assertRaisesRegex(ValueError,'roster'):build([window(1,0,[[],[]],tables=(1,2)),window(2,2,[B,B])])
    def test_fold(self):
        w=window(1,0,[[],B]);w['timeline']['observations'][0]['action_reading']={'candidate':{'action':'fold'}};s=build([w])['segments'][0];self.assertEqual(len(s['fold_label_files']),1);self.assertEqual(len(s['frames']),2);self.assertFalse(s['complete_hand_verified'])

if __name__=='__main__':unittest.main()
