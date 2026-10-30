"""Synthetic, offline tests for the ZIP -> static workspace navigation bridge."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import zipfile
from unittest.mock import patch

import offline_session_bundle as bundle
import offline_session_workspace as workspace
import offline_reviewed_clip_gallery as gallery


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root = self.base / 'clips'; self.root.mkdir()
        self.bundle = self.base / 'session.zip'
        self.dest = self.base / 'workspace'
        (self.root / 'H001.mp4').write_bytes(b'fixture: synthetic MP4 placeholder')
        clip_sha = gallery.sha(self.root / 'H001.mp4')
        source_sha = 'b' * 64
        self.write('manifest.json', {
            'schema_version': 1, 'status': 'human_reviewed_clips_not_verified_hands',
            'source_video_sha256': source_sha,
            'automatic_hand_detection': False, 'equity_or_ev_calculated': False,
            'clips': [{'hand_id': 'H001', 'file': 'H001.mp4',
                       'sidecar': 'H001.mp4.json', 'source_table_id': 'table_1',
                       'clip_sha256': clip_sha}]})
        self.write('H001.mp4.json', {
            'schema_version': 1, 'analysis_status': 'manually_selected_offline_clip',
            'hand_id': 'H001', 'clip_sha256': clip_sha,
            'source_video_sha256': source_sha,
            'video_evidence_verified': False, 'automatic_clip_selection_authorized': False,
            'start_seconds': 1, 'end_seconds': 3,
            'explanation': 'Synthetic example, not a poker hand.'})

    def write(self, name, data):
        (self.root / name).write_text(json.dumps(data), encoding='utf-8')

    def create_bundle(self):
        bundle.export(self.root, self.bundle)

    def test_open_workspace_and_verify(self):
        self.create_bundle()
        result = workspace.open_workspace(self.bundle, self.dest)
        self.assertEqual(result['clips'], 1)
        self.assertEqual(result['conditional_analyses'], 0)
        self.assertFalse(result['action_graded'])
        self.assertTrue((self.dest / 'session' / 'H001.mp4').exists())
        self.assertEqual(workspace.verify_workspace(self.dest)['clips'], 1)

    def test_static_links_and_no_remote_dependencies(self):
        self.create_bundle(); workspace.open_workspace(self.bundle, self.dest)
        page = (self.dest / 'index.html').read_text()
        self.assertIn('href="session/index.html"', page)
        self.assertIn('href="offline_visual_review_ui.html"', page)
        self.assertNotIn('https://', page)
        self.assertIn("default-src 'none'", page)

    def test_no_original_video_copied(self):
        self.create_bundle(); workspace.open_workspace(self.bundle, self.dest)
        self.assertFalse((self.dest / 'source.mp4').exists())
        self.assertFalse((self.dest / 'session' / 'source.mp4').exists())

    def test_reject_existing_workspace(self):
        self.create_bundle(); self.dest.mkdir()
        (self.dest / 'sentinel').write_text('untouched')
        with self.assertRaisesRegex(ValueError, 'new directory'):
            workspace.open_workspace(self.bundle, self.dest)
        self.assertEqual((self.dest / 'sentinel').read_text(), 'untouched')

    def test_reject_tampered_bundle_before_publish(self):
        self.create_bundle()
        with zipfile.ZipFile(self.bundle, 'a') as z:
            z.writestr('untracked.txt', 'tampered')
        with self.assertRaises(ValueError):
            workspace.open_workspace(self.bundle, self.dest)
        self.assertFalse(self.dest.exists())

    def test_reject_missing_review_ui(self):
        self.create_bundle()
        with patch.object(workspace, '__file__', str(self.base / 'missing.py')):
            with self.assertRaisesRegex(ValueError, 'missing regular'):
                workspace.open_workspace(self.bundle, self.dest)
        self.assertFalse(self.dest.exists())

    def test_detect_modified_review_html(self):
        self.create_bundle(); workspace.open_workspace(self.bundle, self.dest)
        (self.dest / workspace.REVIEW_UI).write_text('changed')
        with self.assertRaisesRegex(ValueError, 'integrity mismatch'):
            workspace.verify_workspace(self.dest)

    def test_detect_modified_clip(self):
        self.create_bundle(); workspace.open_workspace(self.bundle, self.dest)
        (self.dest / 'session' / 'H001.mp4').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'integrity mismatch'):
            workspace.verify_workspace(self.dest)

    def test_detect_modified_landing(self):
        self.create_bundle(); workspace.open_workspace(self.bundle, self.dest)
        (self.dest / workspace.LANDING).write_text('changed')
        with self.assertRaisesRegex(ValueError, 'integrity mismatch'):
            workspace.verify_workspace(self.dest)

    def test_detect_added_untracked_file(self):
        self.create_bundle(); workspace.open_workspace(self.bundle, self.dest)
        (self.dest / 'session' / 'extra.txt').write_text('extra')
        with self.assertRaisesRegex(ValueError, 'inventory mismatch'):
            workspace.verify_workspace(self.dest)

    def test_reject_symlinked_session_clip(self):
        self.create_bundle(); workspace.open_workspace(self.bundle, self.dest)
        clip = self.dest / 'session' / 'H001.mp4'
        other = self.base / 'other'; shutil.copyfile(clip, other)
        clip.unlink(); clip.symlink_to(other)
        with self.assertRaisesRegex(ValueError, 'integrity mismatch'):
            workspace.verify_workspace(self.dest)

    def test_cli_open_verify(self):
        self.create_bundle()
        self.assertEqual(workspace.main(['open', str(self.bundle), str(self.dest)]), 0)
        self.assertEqual(workspace.main(['verify', str(self.dest)]), 0)

    def test_reject_symlinked_destination(self):
        self.create_bundle(); self.dest.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'new directory'):
            workspace.open_workspace(self.bundle, self.dest)

    def test_reject_missing_parent(self):
        self.create_bundle()
        with self.assertRaisesRegex(ValueError, 'new directory'):
            workspace.open_workspace(self.bundle, self.base / 'missing' / 'new')

    def test_source_bundle_unmodified(self):
        self.create_bundle(); original = workspace.sha(self.bundle)
        workspace.open_workspace(self.bundle, self.dest)
        self.assertEqual(original, workspace.sha(self.bundle))


if __name__ == '__main__':
    unittest.main()
