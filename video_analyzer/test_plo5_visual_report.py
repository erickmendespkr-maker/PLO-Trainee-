import tempfile
import unittest
from pathlib import Path
from plo5_visual_report import render,sha


class VisualReportTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.out=self.root/'out';self.data=b'fixture crop';(self.root/'a.png').write_bytes(self.data);(self.root/'b.png').write_bytes(self.data)
        self.samples=[{'file':f'{n}.png','sha256':sha(self.data),'table_id':1,'actual_frame_timestamp_seconds':i} for i,n in enumerate('ab')]
        self.drafts={'drafts':[{'draft_id':'d1','frames':[{'file':'a.png'}]}],'unassigned':[{'file':'b.png'}]}
        self.study={'input_digest':'x','decisions':[{'action_file':'a.png','draft_id':'d1','classification':'NO_MATCH','text':'<script>bad</script>'}]}
        self.binding={'job_id':'j','source_sha256':'s'}
    def run_report(self,check=lambda:None):
        return render(self.binding,self.samples,self.drafts,self.study,self.root,self.out,recheck=check)
    def test_export(self):
        r=self.run_report();self.assertEqual(len(r['prints']),2);self.assertEqual(r['decisions_linked'],1);self.assertEqual(r['mp4_rendered'],0)
        h=(self.out/'index.html').read_text();self.assertIn('&lt;script&gt;bad',h);self.assertIn('SEM_DECISAO_VINCULADA',h);self.assertNotIn('<script>bad',h)
        for p in r['prints']:self.assertEqual(sha((self.out/p['file']).read_bytes()),p['sha256'])
        with self.assertRaises(ValueError):self.run_report()
    def test_tamper(self):
        (self.root/'a.png').write_bytes(b'changed')
        with self.assertRaises(ValueError):self.run_report()
        self.assertFalse(self.out.exists())
    def test_wrong_decision(self):
        self.study['decisions'][0]['draft_id']='other'
        with self.assertRaises(ValueError):self.run_report()
    def test_unassigned(self):
        self.study['decisions'][0]['action_file']='b.png';self.study['decisions'][0]['draft_id']=None
        with self.assertRaises(ValueError):self.run_report()
    def test_recheck(self):
        def fail():raise ValueError('changed')
        with self.assertRaises(ValueError):self.run_report(fail)
        self.assertFalse(self.out.exists())
    def test_incomplete(self):
        self.drafts['unassigned']=[]
        with self.assertRaises(ValueError):self.run_report()

if __name__=='__main__':unittest.main()
