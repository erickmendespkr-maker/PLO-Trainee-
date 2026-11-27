import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
import numpy as np
from plo5_payout_reference import PROFILE,feature,distance,load_bank,classify,scan,run

class ReferenceTests(unittest.TestCase):
    def setUp(self):
        self.a=np.random.default_rng(4).random((12,43),dtype=np.float32)
        self.b=np.random.default_rng(5).random((12,43),dtype=np.float32)
        self.bank={'2.5':[self.a],'3.5':[self.b]}
    def test_same_reference_not_verified(self):
        with patch('plo5_payout_reference.feature',return_value=self.a):r=classify(None,self.bank)
        self.assertEqual(r['reference_amount_candidate'],'2.5');self.assertTrue(r['reference_only']);self.assertFalse(r['payout_verified'])
    def test_ambiguity_rejected(self):
        with patch('plo5_payout_reference.feature',return_value=self.a):r=classify(None,{'2.5':[self.a],'3.5':[self.a]})
        self.assertIsNone(r['reference_amount_candidate'])
    def test_unknown_rejected(self):
        with patch('plo5_payout_reference.feature',return_value=np.ones((12,60),np.float32)):r=classify(None,self.bank)
        self.assertIsNone(r['reference_amount_candidate'])
    def test_no_yellow(self):
        self.assertIsNone(feature(Image.new('RGB',(80,25),'green')))
    def test_width_and_distance(self):
        self.assertEqual(distance(self.a,self.a),0);self.assertEqual(distance(self.a,np.ones((12,50),np.float32)),1.)
    def test_bank_validation(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'bank.json';row={'width':43,'pixels':np.round(self.a*255).astype('uint8').tobytes().hex()};data={'profile':PROFILE,'templates':{'2.5':[row],'3.5':[row]}};p.write_text(json.dumps(data));self.assertEqual(set(load_bank(p)),{'2.5','3.5'});data['templates']['-1']=[row];p.write_text(json.dumps(data))
            with self.assertRaises(ValueError):load_bank(p)
    def test_geometry_and_platform(self):
        with self.assertRaises(ValueError):scan(Image.new('RGB',(372,696)),1,self.bank)
        with patch('plo5_payout_reference.detect',return_value='suprema'):self.assertEqual(scan(Image.new('RGB',(1504,696)),1,self.bank),[])
    def test_invalid_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d)/'manifest.json').write_text('{"variant":6}');
            with self.assertRaises(ValueError):run(d,'unused')
if __name__=='__main__':unittest.main()
