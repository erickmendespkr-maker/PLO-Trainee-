import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from plo5_launcher import command, preflight

class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        for name in ('plo5_windows_candidate.py','plo5_review_pipeline.py','clip file.mp4','layout.json','job.json','windows.json','study.json'):(self.root/name).write_text('')
        self.out=self.root/'new output'
    def test_audit(self):
        args,out=command('audit',self.root/'clip file.mp4',self.root/'layout.json',self.out,root=self.root)
        self.assertEqual(args[3],'audit');self.assertEqual(args[4],str(self.root/'clip file.mp4'));self.assertEqual(args[-1],out)
    def test_review(self):
        args,out=command('review',self.root/'job.json',self.root/'windows.json',self.out,mode='deep',extract=True,study=self.root/'study.json',root=self.root)
        self.assertEqual(args[-5:],['--mode','deep','--extract','--study',str(self.root/'study.json')]);self.assertIn(out,args)
    def test_existing(self):
        self.out.mkdir()
        with self.assertRaises(ValueError):command('audit',self.root/'clip file.mp4',self.root/'layout.json',self.out,root=self.root)
    def test_invalid_input(self):
        with self.assertRaises(ValueError):command('audit',self.root/'job.json',self.root/'layout.json',self.out,root=self.root)
    def test_missing_module(self):
        (self.root/'plo5_windows_candidate.py').unlink()
        with self.assertRaises(ValueError):command('audit',self.root/'clip file.mp4',self.root/'layout.json',self.out,root=self.root)
    def test_preflight_missing(self):
        with patch('plo5_launcher.shutil.which',return_value=None):r=preflight(root=self.root)
        self.assertFalse(r['visual_preflight_ok']);self.assertFalse(r['mvp_certified']);self.assertEqual(r['equity_status'],'NOT_PROVIDED')
    def test_bad_equity(self):
        with patch('plo5_launcher.shutil.which',return_value=None):r=preflight(self.root/'job.json',root=self.root)
        self.assertEqual(r['equity_status'],'UNREVIEWED');self.assertFalse(r['windows_verified'])

if __name__=='__main__':unittest.main()
