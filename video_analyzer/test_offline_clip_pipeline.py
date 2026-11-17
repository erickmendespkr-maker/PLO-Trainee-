"""Synthetic FFmpeg/FFprobe integration tests without private footage."""
import hashlib
import subprocess
import tempfile
import unittest
from pathlib import Path
from offline_clip_pipeline import render_candidates


class ClipPipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.video = self.root / 'synthetic.mp4'
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-f', 'lavfi',
                        '-i', 'testsrc2=size=160x120:rate=10', '-t', '3',
                        '-c:v', 'mpeg4', str(self.video)], check=True)
        self.proposal = [{'table_id': 1, 'start_seconds': 0.5,
                          'end_seconds': 2.5, 'evidence_sha256': 'a' * 64}]

    def test_real_ffmpeg_render_and_ffprobe_audit(self):
        report = render_candidates(self.video, self.root / 'clips', self.proposal,
                                   padding_seconds=0)
        self.assertEqual(report['status'], 'candidate_clips_only')
        self.assertEqual(report['video_sha256'], hashlib.sha256(self.video.read_bytes()).hexdigest())
        item = report['results'][0]
        self.assertFalse(item['audit']['content_verified'])
        self.assertFalse(item['audit']['pts_verified'])
        self.assertEqual(item['clip']['review_status'], 'pending_human_review')
        self.assertTrue((self.root / 'clips' / item['file']).is_file())
        self.assertTrue((self.root / 'clips' / 'candidate_clip_report.json').is_file())

    def test_reject_invalid_candidate_before_render(self):
        with self.assertRaises(ValueError):
            render_candidates(self.video, self.root / 'clips',
                              [{**self.proposal[0], 'table_id': 5}])

    def test_no_overwrite(self):
        render_candidates(self.video, self.root / 'clips', self.proposal, padding_seconds=0)
        with self.assertRaises(FileExistsError):
            render_candidates(self.video, self.root / 'clips', self.proposal, padding_seconds=0)

    def test_no_proposals(self):
        report = render_candidates(self.video, self.root / 'empty', [])
        self.assertEqual(report['results'], [])


if __name__ == '__main__':
    unittest.main()
