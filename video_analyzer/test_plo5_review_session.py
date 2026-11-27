import os
import json
import tempfile
import unittest
from pathlib import Path
from hashlib import sha256
from PIL import Image
from unittest.mock import patch
from test_plo5_post_gto_river import polar,CATCH
from test_plo5_reconstruction_candidates import frame
from plo5_review_session import visual_session,review_batch,model_page,table_crop


class SessionReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
    def test_visual_bound_crops(self):
        frames=[frame(0),frame(1,'90')]
        for f in frames:
            p=self.root/f['file'];Image.new('RGB',(1504,696),'red').save(p);f['sha256']=sha256(p.read_bytes()).hexdigest()
        source=self.root/'sample.mp4';source.write_bytes(b'synthetic fixture')
        m=self.root/'manifest.json';m.write_text(json.dumps(dict(variant=5,hands_reconstructed=False,source_sha256=sha256(source.read_bytes()).hexdigest(),frames=frames)))
        html,s=visual_session(m,source);self.assertEqual(s['changes'],1);self.assertEqual(s['unique_crops'],2);self.assertTrue(s['source_hash_checked']);self.assertFalse(s['ev_authorized']);self.assertEqual(html.count('data:image/png;base64,'),2);self.assertIn('<details>',html)
        (self.root/frames[0]['file']).write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError,'hash mismatch'):visual_session(m,source)
        source.write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError,'Source video hash mismatch'):visual_session(m,source)
    def test_model_batch(self):
        base=dict(id='A <test>',context=polar(),history=[['BB','bet',2]],holding=CATCH,action=['call',2],rake_on_fold=False,iterations=100)
        rows=review_batch(self.root/'cache.db',[base,dict(base,id='B',action=['fold',0])]);self.assertFalse(rows[0]['result']['cache_hit']);self.assertTrue(rows[1]['result']['cache_hit']);self.assertAlmostEqual(rows[0]['result']['pot_odds_gross'],1/3)
        html=model_page(rows);self.assertIn('A &lt;test&gt;',html);self.assertIn('Pot odds',html);self.assertIn('<details>',html)
        with self.assertRaises(ValueError):review_batch(self.root/'cache.db',[base,base])
    def test_rank_batch(self):
        index=os.environ.get('PLO5_INDEX_EXE');rank=os.environ.get('PLO5_RANK_EXE')
        if not index or not rank:self.skipTest('native rank binaries absent')
        base=dict(id='A',context=polar(),history=[['BB','bet',2]],holding=CATCH,action=['call',2],rake_on_fold=False,iterations=10)
        from plo5_rank_service import lookup_states
        with patch('plo5_rank_service.lookup_states',wraps=lookup_states) as fn:
            rows=review_batch(self.root/'cache.db',[base,dict(base,id='B')],rank_executables=(index,rank),cfr_executable=os.environ.get('PLO5_MULTIWAY_EXE'))
            self.assertEqual(fn.call_count,1);self.assertEqual(rows[0]['result']['rank'],rows[1]['result']['rank'])
    def test_crop_rejects_path_and_geometry(self):
        p=self.root/'x.png';Image.new('RGB',(10,10)).save(p);f=dict(file=p.name,sha256=sha256(p.read_bytes()).hexdigest())
        with self.assertRaises(ValueError):table_crop(self.root,f,1)
        with self.assertRaises(ValueError):table_crop(self.root,dict(f,file='../x.png'),1)

if __name__=='__main__':unittest.main()
