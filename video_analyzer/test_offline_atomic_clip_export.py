"""Integration tests with real FFmpeg and synthetic video only."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import offline_atomic_clip_export as atomic


class AtomicClipTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.video = self.base / 'synthetic.mp4'
        subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-f','lavfi','-i',
                        'testsrc2=size=320x240:rate=10','-t','3','-c:v','libx264',
                        str(self.video)], check=True)
        h = hashlib.sha256(self.video.read_bytes()).hexdigest()
        self.plan = self.base / 'plan.json'
        self.data = {'schema_version':1,'source_video_sha256':h,'analysis_verified':False,
                     'clip_plans':[{'hand_id':hand,'table_id':1,'clip_start_seconds':0.2,
                                    'clip_end_seconds':1.2,'crop_xywh':[0,0,160,120],
                                    'boundaries_verified':True,'strategy_verified':False,
                                    'analysis_label':'INSUFFICIENT_DATA'} for hand in ('h1','h2')]}
        self.plan.write_text(json.dumps(self.data))
        self.out = self.base / 'out'

    def test_success_with_manifest_last(self):
        result = atomic.export_atomic(self.video,self.plan,self.out)
        self.assertEqual(len(result['clips']),2)
        self.assertEqual(len(list(self.out.glob('*.mp4'))),2)
        self.assertFalse(result['analysis_verified'])
        self.assertTrue((self.out/'clip_manifest.json').exists())
        self.assertFalse(list(self.out.glob('.plo_stage_*')))

    def test_existing_destination_preserved(self):
        self.out.mkdir()
        existing = self.out/'table1_h2.mp4'
        existing.write_bytes(b'original')
        with self.assertRaises(FileExistsError):
            atomic.export_atomic(self.video,self.plan,self.out)
        self.assertEqual(existing.read_bytes(),b'original')
        self.assertFalse((self.out/'table1_h1.mp4').exists())
        self.assertFalse((self.out/'clip_manifest.json').exists())

    def test_failure_during_publish_rolls_back(self):
        real_link = atomic.os.link
        count = 0
        def failing_link(src,dst):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError('simulated publishing error')
            return real_link(src,dst)
        with patch.object(atomic.os,'link',side_effect=failing_link):
            with self.assertRaises(OSError):
                atomic.export_atomic(self.video,self.plan,self.out)
        self.assertEqual(list(self.out.iterdir()),[])

    def test_render_failure_does_not_publish(self):
        with patch.object(atomic,'export_reviewed_clips',side_effect=RuntimeError('ffmpeg failed')):
            with self.assertRaises(RuntimeError):
                atomic.export_atomic(self.video,self.plan,self.out)
        self.assertEqual(list(self.out.iterdir()),[])

    def test_manifest_publish_failure_rolls_back(self):
        real_link = atomic.os.link
        def fail_manifest(src,dst):
            if Path(dst).name == 'clip_manifest.json':
                raise OSError('manifest publication failed')
            return real_link(src,dst)
        with patch.object(atomic.os,'link',side_effect=fail_manifest):
            with self.assertRaises(OSError):
                atomic.export_atomic(self.video,self.plan,self.out)
        self.assertEqual(list(self.out.iterdir()),[])


if __name__=='__main__':
    unittest.main()
