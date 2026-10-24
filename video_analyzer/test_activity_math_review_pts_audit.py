"""Synthetic-only tests for audited decoded FFmpeg timestamps."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from activity_hand_review_packet import build_hand_review_packet
from activity_math_readiness_triage import build_math_readiness_triage
from activity_math_review_handoff import build_math_review_handoff
from activity_math_review_frames import export_math_review_frames
from activity_math_review_pts_audit import audit_math_review_pts, _parse_decoded_pts
from test_activity_consistency_frame_review import changed


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg required')
class MathReviewPtsAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.video = cls.root / 'synthetic.mp4'
        subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
                        '-f', 'lavfi', '-i', 'testsrc2=size=160x120:rate=7:duration=5',
                        '-c:v', 'mpeg4', '-y', str(cls.video)],
                       check=True, capture_output=True)
        sha = hashlib.sha256(cls.video.read_bytes()).hexdigest()
        queue, timeline = changed()
        queue['recording_sha256'] = sha
        timeline['recording_sha256'] = sha
        packet = build_hand_review_packet(queue, timeline)
        triage = build_math_readiness_triage(packet, timeline)
        handoff = build_math_review_handoff(triage, packet, timeline)
        cls.sources = []
        for name, data in [('handoff', handoff), ('triage', triage),
                           ('packet', packet), ('timeline', timeline)]:
            path = cls.root / (name + '.json')
            path.write_text(json.dumps(data), encoding='utf-8')
            cls.sources.append(path)
        cls.frames_dir = cls.root / 'frames'
        export_math_review_frames(cls.video, *cls.sources, cls.frames_dir)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.tmp2 = tempfile.TemporaryDirectory(dir=self.root)
        self.work = Path(self.tmp2.name)

    def tearDown(self):
        self.tmp2.cleanup()

    def audit(self, name='result', frames_dir=None):
        return audit_math_review_pts(self.video, frames_dir or self.frames_dir,
                                     *self.sources, self.work / name)

    def test_real_ffmpeg_pts_byte_identical_and_four_table_handoff(self):
        report = self.audit()
        self.assertEqual(report['counts']['frames_checked'], 1)
        self.assertEqual(report['counts']['byte_identical_decodes'], 1)
        row = report['frames'][0]
        self.assertTrue(row['png_bytes_match'])
        self.assertIsInstance(row['decoded_frame_pts_seconds'], float)
        self.assertAlmostEqual(row['decoded_frame_pts_ticks'] *
                               (lambda a, b: int(a)/int(b))(*row['decoded_frame_time_base'].split('/')),
                               row['decoded_frame_pts_seconds'], places=5)
        self.assertEqual(json.loads((self.work/'result'/'math_review_pts_audit.json').read_text()), report)
        self.assertFalse(report['ready_for_equity_or_ev'])
        self.assertFalse(report['automatic_clip_selection_authorized'])
        with self.assertRaises(ValueError):
            self.audit()

    def test_tampered_manifest_rejected_before_decoding(self):
        alt = self.work / 'altered'
        alt.mkdir()
        manifest = json.loads((self.frames_dir/'math_review_frames.json').read_text())
        (alt/'frame_0000.png').write_bytes((self.frames_dir/'frame_0000.png').read_bytes())
        manifest['frames'][0]['requested_seek_pts_seconds'] += 0.1
        (alt/'math_review_frames.json').write_text(json.dumps(manifest))
        with self.assertRaises(ValueError):
            self.audit(frames_dir=alt)
        self.assertFalse((self.work/'result').exists())

    def test_tampered_png_rejected(self):
        alt = self.work / 'altered'
        shutil.copytree(self.frames_dir, alt)
        with (alt/'frame_0000.png').open('ab') as stream:
            stream.write(b'tamper')
        with self.assertRaises(ValueError):
            self.audit(frames_dir=alt)
        self.assertFalse((self.work/'result').exists())

    def test_byte_mismatch_with_consistent_manifest_withholds_pts(self):
        alt = self.work / 'changed_png'
        shutil.copytree(self.frames_dir, alt)
        png = alt/'frame_0000.png'
        png.write_bytes(png.read_bytes() + b'extra_metadata_bytes')
        manifest_path = alt/'math_review_frames.json'
        manifest = json.loads(manifest_path.read_text())
        manifest['frames'][0]['sha256'] = hashlib.sha256(png.read_bytes()).hexdigest()
        manifest_path.write_text(json.dumps(manifest))
        report = self.audit(frames_dir=alt)
        self.assertEqual(report['counts']['unverified_pts'], 1)
        self.assertFalse(report['frames'][0]['png_bytes_match'])
        self.assertIsNone(report['frames'][0]['decoded_frame_pts_seconds'])
        self.assertFalse(report['ready_for_equity_or_ev'])

    def test_symlink_rejected(self):
        alias = self.work / 'alias'
        alias.symlink_to(self.frames_dir, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.audit(frames_dir=alias)

    def test_parse_rejects_ambiguous_and_nonfinite_pts(self):
        log = 'config in time_base: 1/14336\n[Parsed_showinfo_0] n: 0 pts: 18432 pts_time:1.285714 duration: 2048'
        self.assertEqual(_parse_decoded_pts(log), (18432, 1.285714, '1/14336'))
        with self.assertRaises(ValueError):
            _parse_decoded_pts(log + '\n' + log)
        with self.assertRaises(ValueError):
            _parse_decoded_pts('config in time_base: 1/1\n[Parsed_showinfo_0] n: 0 pts: 1 pts_time:nan')
        with self.assertRaises(ValueError):
            _parse_decoded_pts('config in time_base: 1/1000\n[Parsed_showinfo_0] n: 0 pts: 1 pts_time:1.0')

    def test_cli_and_source_integrity(self):
        out = self.work/'cli'
        run = subprocess.run([sys.executable, str(Path(__file__).with_name('activity_math_review_pts_audit.py')),
                              str(self.video), str(self.frames_dir),
                              *map(str, self.sources), str(out)],
                             capture_output=True, text=True, timeout=60)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)['frames_checked'], 1)
        self.assertFalse(json.loads((out/'math_review_pts_audit.json').read_text())['strategic_error_established'])


if __name__ == '__main__':
    unittest.main()
