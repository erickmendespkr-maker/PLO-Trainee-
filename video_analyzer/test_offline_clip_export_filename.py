import tempfile
import unittest
from pathlib import Path
from offline_clip_export import export_clip

class FilenameHardening(unittest.TestCase):
    def test_reject_control_chars_without_ffmpeg(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td)/'input.mp4'
            source.write_bytes(b'fake video')
            import hashlib
            sha = hashlib.sha256(source.read_bytes()).hexdigest()
            for name in ['line\nbreak.mp4', 'tab\tname.mp4', 'del\x7fname.mp4', 'a'*121+'.mp4']:
                with self.subTest(name=repr(name)):
                    with self.assertRaises(ValueError):
                        export_clip(source, Path(td)/'output', {'source_sha256':sha,'strategic_verdict_allowed':False,'output_name':name,'start_seconds':0,'end_seconds':1,'duration_seconds':1,'review_status':'insufficient_data'})

if __name__ == '__main__': unittest.main()
