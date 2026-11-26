import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from plo5_rank_recalibration import rebuild
from plo5_fourcolor_cards import classify


class RecalibrationTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name)
        p=self.root/'0001.png';Image.new('RGB',(1504,696)).save(p)
        self.row={'requested_seconds':1,'partition':'train','sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'truth':[['Ac Kd Qh Js Tc','2c 3d 4s'],['?','?'],['?','?'],['?','?']]}
    def test_train_bound_labels(self):
        with patch('plo5_rank_recalibration.train',return_value={'A':[(b'\xff'*480,1,'hero')]}) as m:
            b=rebuild([self.row],self.root);self.assertEqual(b['A'][0][0],'ff'*480);self.assertEqual(len(m.call_args.args[0]),2)
    def test_reject_holdout(self):
        self.row['partition']='holdout'
        with self.assertRaisesRegex(ValueError,'training'):rebuild([self.row],self.root)
    def test_hash_mismatch(self):
        self.row['sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'Changed'):rebuild([self.row],self.root)
    def test_physical_collision(self):
        self.row['truth'][0][1]='Ac 3d 4s'
        with self.assertRaisesRegex(ValueError,'Duplicate'):rebuild([self.row],self.root)
    def test_duplicate_timestamp(self):
        with self.assertRaisesRegex(ValueError,'increasing'):rebuild([self.row,self.row],self.root)
    def test_high_distance_and_low_margin_rejected(self):
        g=b'\xff'*480;bank={'A':[(g,1,'hero')],'K':[(b'\x00'*480,1,'hero')]}
        for d,gap in ((.36,.2),(.2,.07)):
            with patch('plo5_fourcolor_cards.feature',return_value=('h','h',(g,1),.8,.8,False)),patch('plo5_fourcolor_cards.distance',side_effect=[d,d+gap]):
                self.assertIsNone(classify(None,1,'hero',0,bank)['card'])


if __name__=='__main__':unittest.main()
