import hashlib,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from plo5_dim_recalibration import dim,extend
from plo5_fourcolor_cards import RANKS

class DimTests(unittest.TestCase):
    def test_dim_background(self):
        for n,expected in ((128,True),(250,False),(45,False)):
            self.assertEqual(dim(Image.new('RGB',(15,17),(n,n,n))),expected)
        self.assertFalse(dim(Image.new('RGB',(15,17),(20,120,30))))
    def sample(self,folder):
        p=Path(folder)/'frame.png';Image.new('RGB',(1504,696),(128,128,128)).save(p)
        return {'file':p.name,'table_id':1,'hero_cards':['Ac','Kd','Qh','Js','Tc'],'partition':'train','sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
    def bank(self):return {r:[(bytes([1])*480,1.,'hero')] for r in RANKS}
    def test_add_only_matching_dim_glyph(self):
        with tempfile.TemporaryDirectory() as d:
            row=self.sample(d);bank=self.bank();sig=(bytes([2])*480,1.)
            with patch('plo5_dim_recalibration.detect',return_value='pppoker'),patch('plo5_dim_recalibration.feature',return_value=('c','c',sig,.7,.7,False)):
                result=extend(bank,[row],d)
            self.assertEqual(len(result['A']),2);self.assertEqual(len(result['T']),2);self.assertEqual(len(result['K']),1);self.assertEqual(len(bank['A']),1)
    def test_bright_roi_excluded(self):
        with tempfile.TemporaryDirectory() as d:
            row=self.sample(d);bank=self.bank()
            with patch('plo5_dim_recalibration.detect',return_value='pppoker'),patch('plo5_dim_recalibration.dim',return_value=False),patch('plo5_dim_recalibration.feature') as m:
                self.assertEqual(extend(bank,[row],d),bank);m.assert_not_called()
    def test_reject_unbound_and_holdout(self):
        with tempfile.TemporaryDirectory() as d:
            row=self.sample(d)
            for changes in ({'sha256':'bad'},{'partition':'holdout'},{'file':'../frame.png'},{'hero_cards':['Ac']*5}):
                with self.assertRaises(ValueError):extend(self.bank(),[dict(row,**changes)],d)
    def test_no_duplicate_calibration_rows(self):
        with tempfile.TemporaryDirectory() as d:
            row=self.sample(d)
            with patch('plo5_dim_recalibration.detect',return_value='pppoker'):
                with self.assertRaises(ValueError):extend(self.bank(),[row,row],d)
if __name__=='__main__':unittest.main()
