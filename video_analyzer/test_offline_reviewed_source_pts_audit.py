"""FFprobe-backed synthetic PTS checks. No real PLO recording is available."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import test_offline_reviewed_decision_timeline as timeline_fixture
from offline_reviewed_source_pts_audit import (
    _scan_pts, build_report, export, main, recording_hash, render_html)


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),
                     'FFmpeg and FFprobe required')
class SourcePtsAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.video = self.root / 'source.mp4'
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
                        '-f', 'lavfi', '-i', 'testsrc2=size=160x90:rate=10:duration=3',
                        '-c:v', 'mpeg4', str(self.video)], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        self.fixture = timeline_fixture.DecisionTimelineTests('test_success_and_blocked_sorted')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        # The original fixture's root is distinct; move the source to its root
        # so create-only output remains alongside pipeline directories.
        self.video2 = self.fixture.root / 'source.mp4'
        shutil.copyfile(self.video, self.video2)
        self.fixture.source = hashlib.sha256(self.video2.read_bytes()).hexdigest()

    def make(self, name='hand1', table=1, label='h1', moment=1.5, blocked=False):
        return self.fixture.make(name, table, label, moment, blocked)

    def report(self, **kwargs):
        return build_report(self.video2, self.fixture.dirs, **kwargs)

    def test_real_ffprobe_frames_nearest(self):
        self.make()
        r = self.report()
        self.assertEqual(r['frame_scan']['decoded_frames_scanned'], 30)
        self.assertEqual(r['timestamps_checked'], 3)
        self.assertEqual(r['timestamps_outside_tolerance'], 0)
        self.assertEqual([x['nearest_frame_index'] for x in r['hands'][0]['frame_pts_checks']],
                         [5, 15, 25])
        self.assertTrue(r['source_file_sha256_verified'])
        self.assertFalse(r['video_content_verified'])

    def test_two_tables_and_blocked(self):
        self.make('first', 1, 'h1', 1.2)
        self.make('second', 4, 'h2', 1.8)
        self.make('blocked', 2, 'h3', 2.0, True)
        r = self.report()
        self.assertEqual((r['hand_count'], r['exported_clip_count'], r['timestamps_checked']),
                         (3, 2, 6))
        self.assertEqual(len(r['hands'][2]['frame_pts_checks']), 0)
        self.assertFalse(r['hands'][2]['all_declared_times_near_decoded_frames'])

    def test_outside_duration_is_review_warning_not_false_proof(self):
        self.make(moment=7)
        r = self.report()
        self.assertEqual(r['timestamps_outside_tolerance'], 3)
        self.assertFalse(r['hands'][0]['all_declared_times_near_decoded_frames'])

    def test_tolerance_configurable(self):
        self.make(moment=1.55)
        self.assertEqual(self.report(tolerance_seconds=0.02)['timestamps_outside_tolerance'], 3)
        self.assertEqual(self.report(tolerance_seconds=0.06)['timestamps_outside_tolerance'], 0)

    def test_source_digest_mismatch_rejected(self):
        self.make()
        other = self.fixture.root / 'different.mp4'
        other.write_bytes(self.video2.read_bytes() + b'x')
        with self.assertRaisesRegex(ValueError, 'SHA-256 differs'):
            build_report(other, self.fixture.dirs)

    def test_tampered_clip_rejected(self):
        folder = self.make()
        (folder / 'clip.mp4').write_bytes(b'corrupted')
        with self.assertRaisesRegex(ValueError, 'digest mismatch'):
            self.report()

    def test_symlink_recording_rejected(self):
        self.make()
        link = self.fixture.root / 'link.mp4'
        link.symlink_to(self.video2)
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            build_report(link, self.fixture.dirs)

    def test_wrong_extension_rejected(self):
        self.make()
        other = self.fixture.root / 'video.txt'
        other.write_bytes(self.video2.read_bytes())
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            build_report(other, self.fixture.dirs)

    def test_export_json_and_html_create_only(self):
        self.make()
        out = self.fixture.root / 'pts.json'
        page = self.fixture.root / 'pts.html'
        r = export(self.video2, self.fixture.dirs, out, page)
        self.assertEqual(json.loads(out.read_text()), r)
        self.assertIn('PTS offline', page.read_text())
        self.assertIn('./hand1/clip.mp4', page.read_text())
        before = out.read_bytes()
        with self.assertRaisesRegex(ValueError, 'new local file'):
            export(self.video2, self.fixture.dirs, out, page)
        self.assertEqual(out.read_bytes(), before)

    def test_no_partial_export_when_html_exists(self):
        self.make()
        page = self.fixture.root / 'pts.html'
        page.write_text('original')
        out = self.fixture.root / 'pts.json'
        with self.assertRaisesRegex(ValueError, 'new local file'):
            export(self.video2, self.fixture.dirs, out, page)
        self.assertFalse(out.exists())
        self.assertEqual(page.read_text(), 'original')

    def test_reject_output_outside_pipeline_root(self):
        self.make()
        with self.assertRaisesRegex(ValueError, 'new local file'):
            export(self.video2, self.fixture.dirs, self.root / 'pts.json',
                   self.fixture.root / 'pts.html')

    def test_reject_symlink_output(self):
        self.make()
        output = self.fixture.root / 'pts.json'
        output.symlink_to(self.video2)
        with self.assertRaisesRegex(ValueError, 'new local file'):
            export(self.video2, self.fixture.dirs, output,
                   self.fixture.root / 'pts.html')

    def test_escape_untrusted_hand_label(self):
        self.make(label='<img src=x onerror=alert(1)>')
        page = render_html(self.report())
        self.assertNotIn('<img', page)
        self.assertIn('&lt;img', page)

    def test_reject_invalid_tolerance(self):
        self.make()
        for tolerance in (0, -1, 3, float('nan'), True):
            with self.subTest(tolerance=tolerance):
                with self.assertRaises(ValueError):
                    self.report(tolerance_seconds=tolerance)

    def test_reject_frame_limit(self):
        self.make()
        with self.assertRaisesRegex(ValueError, 'Frame count exceeds'):
            self.report(max_frames=2)

    def test_reject_bad_timeout(self):
        self.make()
        with self.assertRaisesRegex(ValueError, 'Invalid ffprobe timeout'):
            self.report(timeout_seconds=0)

    def test_missing_ffprobe_fails_without_outputs(self):
        self.make()
        with self.assertRaises(FileNotFoundError):
            export(self.video2, self.fixture.dirs, self.fixture.root / 'pts.json',
                   self.fixture.root / 'pts.html', ffprobe='/no/such/ffprobe')
        self.assertFalse((self.fixture.root / 'pts.json').exists())

    def test_cli_creates_both_outputs(self):
        self.make()
        rc = main([str(self.video2), str(self.fixture.root / 'pts.json'),
                   str(self.fixture.root / 'pts.html'),
                   *map(str, self.fixture.dirs)])
        self.assertEqual(rc, 0)
        self.assertTrue((self.fixture.root / 'pts.html').is_file())

    def test_duplicate_pipeline_directory_rejected(self):
        folder = self.make()
        with self.assertRaisesRegex(ValueError, 'Repeated pipeline'):
            build_report(self.video2, [folder, folder])

    def test_no_frame_pts_rejected(self):
        self.make()
        with patch('offline_reviewed_source_pts_audit.subprocess.run') as mocked:
            def fake(cmd, **kwargs):
                return subprocess.CompletedProcess(cmd, 0, b'', b'')
            mocked.side_effect = fake
            with self.assertRaisesRegex(ValueError, 'No decoded video frames'):
                self.report()

    def test_nonmonotonic_pts_rejected(self):
        self.make()
        with patch('offline_reviewed_source_pts_audit.subprocess.run') as mocked:
            def fake(cmd, **kwargs):
                kwargs['stdout'].write(b'0.200000\n0.100000\n')
                return subprocess.CompletedProcess(cmd, 0, b'', b'')
            mocked.side_effect = fake
            with self.assertRaisesRegex(ValueError, 'not monotonic'):
                self.report()

    def test_malformed_pts_rejected(self):
        self.make()
        with patch('offline_reviewed_source_pts_audit.subprocess.run') as mocked:
            def fake(cmd, **kwargs):
                kwargs['stdout'].write(b'not_a_timestamp\n')
                return subprocess.CompletedProcess(cmd, 0, b'', b'')
            mocked.side_effect = fake
            with self.assertRaisesRegex(ValueError, 'invalid frame PTS'):
                self.report()

    def test_ffprobe_failure_rejected(self):
        self.make()
        with patch('offline_reviewed_source_pts_audit.subprocess.run') as mocked:
            mocked.return_value = subprocess.CompletedProcess([], 1, b'', b'error')
            with self.assertRaisesRegex(ValueError, 'frame scan failed'):
                self.report()

    def test_24fps_source(self):
        video = self.fixture.root / 'source24.mp4'
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
                        '-f', 'lavfi', '-i', 'testsrc2=size=160x90:rate=24:duration=3',
                        '-c:v', 'mpeg4', str(video)], check=True, stderr=subprocess.PIPE)
        self.fixture.source = hashlib.sha256(video.read_bytes()).hexdigest()
        self.make()
        r = build_report(video, self.fixture.dirs)
        self.assertEqual(r['frame_scan']['decoded_frames_scanned'], 72)
        self.assertEqual(r['timestamps_outside_tolerance'], 0)

    def test_output_html_contains_no_remote_resources(self):
        self.make()
        page = render_html(self.report())
        self.assertNotIn('<script', page)
        self.assertNotIn('https://', page)
        self.assertIn("connect-src 'none'", page)


if __name__ == '__main__':
    unittest.main()
