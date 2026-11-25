import tempfile
from pathlib import Path
import subprocess
import unittest
from plo5_dense_timeline import extract,timeline

H=['As','Kd','Qc','Jh','Ts']
B=['2s','3d','4c']

def row(i,h=H,b=None,action=None,table=1,visible=True):
    reading={'status':'action_label_candidate' if action else 'uncertain_label','candidate':{'action':action} if action else None}
    return {'file':f'{table}_{i}.png','table_id':table,'pts':i,'visible':visible,'hero_cards':h,'board_cards':b,'action_reading':reading}

class DenseTests(unittest.TestCase):
    def test_fold_and_street_progress(self):
        r=timeline([row(0,b=[]),row(1,b=B,action='fold'),row(2,h=None,b=B,action='fold'),row(3,h=None,b=B+['5h'])]);s=r['segments'][0]
        self.assertEqual(len(r['segments']),1);self.assertTrue(s['frames'][2]['after_fold_label']);self.assertEqual(s['frames'][3]['street_candidate'],'turn');self.assertEqual(len(s['label_episodes']),1);self.assertEqual(s['label_episodes'][0]['observations'],2);self.assertNotIn('seat',s['label_episodes'][0]);self.assertFalse(s['complete_hand_verified'])
    def test_reset_conflict_and_gap(self):
        r=timeline([row(0,b=B),row(1,b=[]),row(2,h=['Ac','Kd','Qc','Jh','Ts'],b=[]),row(6,b=[])]);self.assertEqual([s['start_reason'] for s in r['segments']],['window_start_or_visibility_gap','board_reset_or_conflict','private_cards_conflict','sampling_gap'])
    def test_visibility_and_table_separation(self):
        r=timeline([row(0,b=[],action='fold'),row(1,visible=None),row(2,b=[]),row(0,b=[],table=2)]);self.assertEqual(len(r['segments']),3);self.assertEqual(len(r['unassigned']),1);self.assertFalse(r['segments'][1]['frames'][0]['after_fold_label']);self.assertFalse(r['actions_verified'])
    def test_reject_invalid_cards(self):
        for bad in [row(0,h=H[:4]),row(0,b=['As','2d','3s']),row(0,h=['As']*5)]:
            with self.assertRaises(ValueError):timeline([bad])
    def test_integer_pts_on_real_mp4(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);v=p/'input.mp4';subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=s=128x128:r=10:d=6','-c:v','libx264','-threads','1',str(v)],check=True);d=p/'frames';d.mkdir();out=extract(v,1,3,d,(128,128));self.assertEqual([x['pts'] for x in out],[1,2,3]);self.assertEqual(len(list(d.glob('*.jpg'))),3)
            with self.assertRaises(ValueError):extract(v,1,1,d,(128,128))

if __name__=='__main__':unittest.main()
