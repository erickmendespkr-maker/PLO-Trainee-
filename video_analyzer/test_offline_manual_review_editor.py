"""Offline review editor smoke tests (no GitHub Actions required)."""
import base64
import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from html import unescape
from pathlib import Path
from offline_manual_review_editor import EDITOR_JS, render_editor, build
from offline_human_observation_review import validate_annotations

class EditorTests(unittest.TestCase):
    def test_csp_and_hash(self):
        html = unescape(render_editor())
        digest = base64.b64encode(hashlib.sha256(EDITOR_JS.encode()).digest()).decode()
        self.assertIn("script-src 'sha256-" + digest + "'", html)
        self.assertIn("connect-src 'none'", html)
        self.assertNotIn("https://", html)
        self.assertNotIn("http://", html)

    def test_generate_without_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'editor.html'
            build(out)
            self.assertTrue(out.exists())
            with self.assertRaises(ValueError):
                build(out)

    def test_wrong_extension(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                build(Path(temp) / 'editor.js')

    @unittest.skipUnless(shutil.which('node'), 'Node.js not installed')
    def test_javascript_syntax(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'editor.js'
            path.write_text(EDITOR_JS, encoding='utf-8')
            subprocess.run(['node', '--check', str(path)], check=True)

    def test_manual_annotation_contract(self):
        row = {'table_id':1,'hand_id':'hand1','decision_id':'d1',
               'observed_action':'call','action_pts_seconds':1.0,
               'candidate_window_seconds':[0.25,1.75],
               'clip_window_seconds':[0.0,2.0]}
        source = {(1,'hand1','d1'):row}
        annotation = {'schema_version':1,'source_session_review_sha256':'a'*64,
                      'reviewer_alias':'revisor_teste','entries':[{
                        'table_id':1,'hand_id':'hand1','decision_id':'d1',
                        'outcome':'corrected','corrected_observed_action':'raise',
                        'corrected_action_pts_seconds':1.25,
                        'note':'Corrigido após revisão da gravação.'}]}
        self.assertEqual(len(validate_annotations(annotation,source,'a'*64)),1)
        annotation['entries'][0]['corrected_action_pts_seconds'] = 99
        with self.assertRaises(ValueError):
            validate_annotations(annotation,source,'a'*64)

if __name__ == '__main__':
    unittest.main()
