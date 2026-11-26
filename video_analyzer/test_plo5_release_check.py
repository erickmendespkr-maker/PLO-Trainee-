import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from plo5_release_check import imports, check

class ReleaseCheckTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);self.root=Path(tmp.name)
    def put(self,name,content):
        (self.root/(name+'.py')).write_text(content,encoding='utf-8')
    def test_actual_import(self):
        self.put('simple','VALUE=42\n');self.assertEqual(imports(self.root,['simple'])['simple'],{'ok':True,'status':'IMPORTED'})
    def test_missing_transitive(self):
        self.put('broken','import module_missing_plo5_test_abc\n');r=imports(self.root,['broken'])['broken'];self.assertFalse(r['ok']);self.assertIn('module_missing_plo5_test_abc',r['detail'])
    def test_missing_source(self):
        self.assertEqual(imports(self.root,['missing'])['missing']['status'],'MISSING_SOURCE')
    def test_bad_syntax(self):
        self.put('bad','def (');self.assertEqual(imports(self.root,['bad'])['bad']['status'],'IMPORT_FAILED')
    def test_timeout(self):
        self.put('slow','import time; time.sleep(3)');self.assertEqual(imports(self.root,['slow'],timeout=.2)['slow']['status'],'PROBE_FAILED')
    def test_invalid_names(self):
        for names in [('x.y',),('x','x')]:
            with self.assertRaises(ValueError):imports(self.root,names)
    def test_gate(self):
        env={'visual_preflight_ok':True,'checks':{'tkinter':True},'equity_status':'NOT_PROVIDED'}
        with patch('plo5_release_check.preflight',return_value=env),patch('plo5_release_check.imports',side_effect=[{'x':{'ok':False}},{'y':{'ok':True}}]):r=check(root=self.root)
        self.assertFalse(r['visual_startup_preflight_ok']);self.assertTrue(r['strategy_imports_ok']);self.assertFalse(r['strategy_snapshot_reviewed']);self.assertFalse(r['mvp_certified'])
    def test_no_certification_even_if_imports_pass(self):
        env={'visual_preflight_ok':True,'checks':{'tkinter':True},'equity_status':'REVIEWED_BINARY'}
        with patch('plo5_release_check.preflight',return_value=env),patch('plo5_release_check.imports',return_value={'x':{'ok':True}}):r=check(root=self.root)
        self.assertTrue(r['visual_startup_preflight_ok']);self.assertTrue(r['strategy_imports_ok']);self.assertTrue(r['strategy_snapshot_reviewed']);self.assertFalse(r['complete_session_verified']);self.assertFalse(r['windows_verified'])

if __name__=='__main__':unittest.main()
