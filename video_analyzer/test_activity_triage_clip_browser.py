"""Offline MP4 review packaging: hashes, atomicity, safe HTML, manual playback."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from activity_hypothetical_math import digest
from activity_triage_clip_browser import (
    build_clip_browser_package, write_clip_browser_package, _embed_manual_players, main,
)
from activity_triage_dashboard import build_triage_dashboard
from test_activity_triage_dashboard import fixture


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg required')
class ClipBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source_td = tempfile.TemporaryDirectory()
        cls.clip_bytes = Path(cls.source_td.name) / 'base.mp4'
        subprocess.run([
            'ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi',
            '-i', 'color=c=blue:s=128x96:r=10:d=0.8', '-c:v', 'mpeg4',
            '-q:v', '5', '-pix_fmt', 'yuv420p', '-y', str(cls.clip_bytes),
        ], check=True, timeout=20)
        cls.sha = hashlib.sha256(cls.clip_bytes.read_bytes()).hexdigest()

    @classmethod
    def tearDownClass(cls):
        cls.source_td.cleanup()

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)
        self.root = Path(self.td.name)
        self.clips = self.root / 'source_clips'
        self.clips.mkdir()
        self.output = self.root / 'package'
        self.triage = fixture()
        for row in self.triage['candidates']:
            row['original_mp4_sha256'] = self.sha
            shutil.copyfile(self.clip_bytes, self.clips / row['filename'])

    def build(self, data=None, output=None):
        return build_clip_browser_package(data if data is not None else self.triage,
                                          self.clips, output or self.output)

    def test_four_tables_verified_and_manual_video(self):
        manifest = self.build()
        self.assertEqual(manifest['total_decisions'], 4)
        self.assertEqual(manifest['clips_copied'], 4)
        self.assertEqual(manifest['source_triage_sha256'], digest(self.triage))
        self.assertFalse(manifest['strategic_error_established'])
        self.assertFalse(manifest['auto_clip_selection_authorized'])
        self.assertFalse(manifest['visual_evidence_verified'])
        html = (self.output / 'index.html').read_text(encoding='utf-8')
        self.assertEqual(html.count('<video controls'), 4)
        self.assertIn('media-src &#x27;self&#x27;', html)
        self.assertIn('connect-src &#x27;none&#x27;', html)
        self.assertNotIn('autoplay', html)
        self.assertNotIn('https://', html)
        self.assertEqual(hashlib.sha256((self.output / 'index.html').read_bytes()).hexdigest(),
                         manifest['html_sha256'])
        for clip in manifest['clips']:
            self.assertEqual(clip['sha256'], self.sha)
            self.assertEqual(clip['width'], 128)
            self.assertEqual(clip['height'], 96)
            self.assertGreater(clip['duration_seconds'], 0)
            self.assertEqual(hashlib.sha256((self.output/'clips'/clip['filename']).read_bytes()).hexdigest(), self.sha)

    def test_legacy_dashboard_still_forbids_media(self):
        html = build_triage_dashboard(self.triage)['html']
        self.assertIn('media-src &#x27;none&#x27;', html)
        self.assertNotIn('<video', html)

    def test_unknown_verified_clip_rejected(self):
        with self.assertRaises(ValueError):
            _embed_manual_players(build_triage_dashboard(self.triage)['html'], self.triage, {'other.mp4'})

    def test_bad_verified_clip_filename_rejected(self):
        with self.assertRaises(ValueError):
            _embed_manual_players(build_triage_dashboard(self.triage)['html'], self.triage, {'../../evil.mp4'})

    def test_wrong_sha_no_partial_output(self):
        self.triage['candidates'][0]['original_mp4_sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
            self.build()
        self.assertFalse(self.output.exists())

    def test_missing_clip_no_partial_output(self):
        (self.clips/self.triage['candidates'][1]['filename']).unlink()
        with self.assertRaisesRegex(ValueError, 'Missing'):
            self.build()
        self.assertFalse(self.output.exists())

    def test_source_symlink_rejected(self):
        filename = self.triage['candidates'][0]['filename']
        (self.clips/filename).unlink()
        (self.clips/filename).symlink_to(self.clip_bytes)
        with self.assertRaises(ValueError):
            self.build()
        self.assertFalse(self.output.exists())

    def test_source_dir_symlink_rejected(self):
        alias = self.root / 'alias'
        alias.symlink_to(self.clips, target_is_directory=True)
        with self.assertRaises(ValueError):
            build_clip_browser_package(self.triage, alias, self.output)

    def test_existing_output_preserved(self):
        self.output.mkdir()
        marker = self.output / 'keep.txt'
        marker.write_text('do not touch')
        with self.assertRaisesRegex(ValueError, 'must not exist'):
            self.build()
        self.assertEqual(marker.read_text(), 'do not touch')

    def test_output_nested_under_source_rejected(self):
        with self.assertRaisesRegex(ValueError, 'inside'):
            self.build(output=self.clips/'nested')

    def test_invalid_video_rejected_even_when_sha_matches(self):
        name = self.triage['candidates'][0]['filename']
        (self.clips/name).write_bytes(b'not an MP4 file')
        self.triage['candidates'][0]['original_mp4_sha256'] = hashlib.sha256(b'not an MP4 file').hexdigest()
        with self.assertRaisesRegex(ValueError, 'Invalid or unreadable MP4'):
            self.build()
        self.assertFalse(self.output.exists())

    def test_duplicate_filename_same_hash_is_deduplicated(self):
        row = copy.deepcopy(self.triage['candidates'][0])
        row['hand_id'] = 'h1_extra'
        self.triage['candidates'].insert(1, row)
        self.assertEqual(self.build()['clips_copied'], 4)
        html = (self.output/'index.html').read_text()
        self.assertEqual(html.count('<video controls'), 5)

    def test_duplicate_filename_conflicting_sha_rejected(self):
        row = copy.deepcopy(self.triage['candidates'][0])
        row['hand_id'] = 'h1_extra'
        row['original_mp4_sha256'] = 'f'*64
        self.triage['candidates'].insert(1, row)
        with self.assertRaisesRegex(ValueError, 'Conflicting SHA'):
            self.build()
        self.assertFalse(self.output.exists())

    def test_expected_triage_digest_mismatch(self):
        with self.assertRaisesRegex(ValueError, 'mismatch'):
            build_clip_browser_package(self.triage, self.clips, self.output,
                                       expected_sha256='f'*64)

    def test_cli_writes_package(self):
        source = self.root/'triage.json'
        source.write_text(json.dumps(self.triage))
        self.assertEqual(main([str(source), str(self.clips), str(self.output),
                               '--expected-sha256', digest(self.triage)]), 0)
        self.assertTrue((self.output/'index.html').is_file())
        self.assertEqual(json.loads((self.output/'manifest.json').read_text())['clips_copied'], 4)

    def test_cli_rejects_linked_json(self):
        source = self.root/'triage.json'
        source.write_text(json.dumps(self.triage))
        alias = self.root/'linked.json'
        alias.symlink_to(source)
        with self.assertRaises(ValueError):
            write_clip_browser_package(alias, self.clips, self.output)

    def test_no_auto_approval_in_export_notes(self):
        self.build()
        html = (self.output/'index.html').read_text()
        for name in ('visual_evidence_verified: false', 'strategic_error_established: false',
                     'ev_ranking_authorized: false', 'clip_selection_authorized: false'):
            self.assertIn(name, html)

    def test_xss_in_hand_and_reason_is_escaped(self):
        self.triage['candidates'][0]['hand_id'] = '<svg onload=alert(1)>'
        self.triage['candidates'][0]['reason'] = '</details><script>alert(1)</script>'
        self.build()
        html = (self.output/'index.html').read_text()
        self.assertNotIn('<svg onload=', html)
        self.assertNotIn('</details><script>', html)
        self.assertIn('&lt;svg', html)

    def test_empty_triage_creates_empty_package(self):
        self.triage['candidates'] = []
        self.assertEqual(self.build()['clips_copied'], 0)
        self.assertEqual(list((self.output/'clips').iterdir()), [])
        self.assertIn('media-src &#x27;none&#x27;', (self.output/'index.html').read_text())


if __name__ == '__main__':
    unittest.main()
