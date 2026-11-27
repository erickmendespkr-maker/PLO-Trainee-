
import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from plo5_selective_study_report import build, video_report, records_from
from plo5_error_prints import bind, capture
from plo5_video_stream import scan
from plo5_selective_review import VERSION
from test_plo5_error_prints import FixtureReader
from test_plo5_selective_review import row


class ReportTests(unittest.TestCase):
    def test_error_only_groups_and_details(self):
        a=row('flop','m');b=row('river','g',alt=(7,7));c=row('turn','adequate-only',lo=2,hi=2);d=row('turn','pending-only',hi=1)
        for r in (a,b,c,d):r['evidence']=None;r['hand_id']='h<script>alert(1)</script>'
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'study';s=build([a,b,c,d],p,demo=True);h=(p/'index.html').read_text()
            self.assertEqual((s['errors'],s['adequate'],s['unresolved']), (2,1,1));self.assertEqual(h.count('<article>'),2);self.assertEqual(h.count('<section>'),1)
            self.assertIn('marginal',h);self.assertIn('grave',h);self.assertIn('0,01 BB',h);self.assertIn('33,333',h);self.assertIn('Ver fundamentação matemática',h)
            self.assertIn('DEMONSTRAÇÃO FICTÍCIA',h);self.assertNotIn('adequate-only',h);self.assertIn('pending-only',h.split('Diagnóstico separado')[1]);self.assertNotIn('<script>',h);self.assertIn('&lt;script&gt;',h);self.assertFalse(s['drivehud_beta'])
            self.assertEqual(s['decision_prints'],0);self.assertIn('Print pendente',h)
    def test_no_errors_is_not_all_correct(self):
        d=row();d['strategy_verified']=False;d['evidence']=None
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'report';s=build([d],p);h=(p/'index.html').read_text();self.assertEqual(s['errors'],0);self.assertIn('Isso não significa',h);self.assertNotIn('<article>',h);self.assertNotIn('<img',h)
            with self.assertRaises(ValueError):build([d],p)
    def test_contract_and_street_filter(self):
        a=row('flop','a');b=row('river','b');a['evidence']=b['evidence']=None
        self.assertEqual(records_from(dict(version=VERSION,decisions=[a,b])),[a,b]);self.assertEqual(records_from(dict(hands_reconstructed=False,decision_records=[a])),[a])
        with self.assertRaises(ValueError):records_from(dict(version='unsupported',decisions=[a]))
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'report';s=build([a,b],p,['river']);self.assertEqual(s['errors'],1);self.assertNotIn('FLOP ·', (p/'index.html').read_text())


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg absent')
class ReportCaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.root=Path(cls.tmp.name);cls.video=cls.root/'test.mp4'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=s=1504x696:r=4','-t','2','-c:v','libx264','-threads','1','-pix_fmt','yuv420p',str(cls.video)],check=True,timeout=30)
        cls.manifest=scan(cls.video,0,2,reader=FixtureReader());cls.rows=[row('flop','a'),row('flop','b'),row('flop','adequate-only',lo=2,hi=2)]
        for d in cls.rows:d['evidence']=bind(cls.manifest,d,'1',1,'before')
        cls.crops=cls.root/'captures';capture(cls.video,cls.manifest,cls.rows,cls.crops,['flop'])
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def test_exact_crops_and_lazy_loading(self):
        p=self.root/'report';s=build(self.rows,p,['flop'],prints=self.crops/'manifest.json');h=(p/'index.html').read_text()
        self.assertEqual((s['errors'],s['decision_prints'],s['unique_crops']), (2,2,1));self.assertEqual(h.count('loading="lazy"'),2);self.assertNotIn('base64',h)
        assets=list((p/'prints').iterdir());self.assertEqual(len(assets),1);self.assertEqual(assets[0].read_bytes(),(self.crops/assets[0].name).read_bytes())
    def test_reject_tamper_and_wrong_scope(self):
        m=json.loads((self.crops/'manifest.json').read_text());p=self.root/'bad';p.mkdir();mp=p/'manifest.json';name=m['decision_prints'][0]['file'];(p/name).write_bytes(b'bad')
        mp.write_text(json.dumps(m));out=self.root/'failed'
        with self.assertRaisesRegex(ValueError,'PNG hash mismatch'):build(self.rows,out,['flop'],prints=mp)
        self.assertFalse(out.exists())
        with self.assertRaisesRegex(ValueError,'scope mismatch'):build(self.rows,out,['river'],prints=mp)
        m['decision_prints'][0]['file']='../escape.png';mp.write_text(json.dumps(m))
        with self.assertRaisesRegex(ValueError,'Unsafe print filename'):build(self.rows,out,['flop'],prints=mp)
        self.assertFalse(out.exists())
    def test_integrated_video_no_errors(self):
        with patch('plo5_error_prints.decode') as decoder:
            s=video_report(self.video,self.manifest,[self.rows[-1]],self.root/'empty',['flop']);decoder.assert_not_called()
        self.assertEqual(s['unique_crops'],0);self.assertEqual(s['adequate'],1)

if __name__=='__main__':unittest.main()
