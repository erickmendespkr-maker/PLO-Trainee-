import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
from plo5_mvp import EvidenceReader,review_video,review_models
from test_plo5_reconstruction_candidates import frame
from test_plo5_post_gto_river import polar,CATCH
import json

class MVPTests(unittest.TestCase):
    def test_selective_evidence(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);source=root/'test.mp4';source.write_bytes(b'test')
            image=Image.new('RGB',(1504,696),'red');h=hashlib.sha256(image.tobytes()).hexdigest()
            frames=[frame(0),frame(1,'90'),frame(2,'90')]
            for i,f in enumerate(frames):f.update(file=f'sample_{i:05d}.rgb',rgb_sha256=h)
            from plo5_reconstruction_candidates import collect
            def fake_scan(source,start,seconds,**kwargs):
                import copy
                rows=copy.deepcopy(frames);reader=kwargs.get('reader')
                if reader:
                    for f in rows:reader.scan(image)
                return dict(variant=5,source_sha256=hashlib.sha256(b'test').hexdigest(),frames=rows,evidence=collect(rows),hands_reconstructed=False)
            with patch('plo5_mvp.scan',side_effect=fake_scan):r=review_video(source,root/'out')
            self.assertEqual(r['selected_pngs'],2);self.assertEqual(r['sampled_frames'],3);self.assertFalse(r['ev_authorized'])
            self.assertEqual(len(list((root/'out').glob('*.png'))),2);self.assertTrue((root/'out/index.html').is_file())
            self.assertIn('sample_00002.rgb',(root/'out/manifest.json').read_text())
    def test_rgb_mismatch(self):
        with tempfile.TemporaryDirectory() as t:
            f=dict(file='x.rgb',rgb_sha256='0'*64,observations=[])
            with self.assertRaisesRegex(ValueError,'RGB evidence mismatch'):EvidenceReader({'frames':[f]},{'x.rgb'},Path(t)).scan(Image.new('RGB',(1,1)))
    def test_models(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);p=root/'models.json';p.write_text(json.dumps(dict(decisions=[dict(id='test',context=polar(),history=[['BB','bet',2]],holding=CATCH,action=['call',2],rake_on_fold=False,iterations=10)])))
            r=review_models(p,root/'out.html',root/'cache.sqlite');self.assertEqual(r['decisions'],1);self.assertFalse(r['gto_solution']);self.assertIn('Pot odds',(root/'out.html').read_text())
            with self.assertRaises(ValueError):review_models(p,root/'out.html',root/'cache.sqlite')
if __name__=='__main__':unittest.main()
