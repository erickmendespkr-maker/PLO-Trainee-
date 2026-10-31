"""Synthetic regression tests for offline session overview."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest

import offline_ev_batch_clips as batch
import offline_ev_session_overview as overview
from test_offline_ev_batch_clips import BatchTests


class OverviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = BatchTests('test_two_mp4s_and_hashes')
        cls.fixture.setUp()
        if not cls.fixture.has_ffmpeg:
            raise unittest.SkipTest('FFmpeg required')
        cls.fixture.make([('T1','H1',1.0,'call',.5,.5),
                          ('T2','H2',2.0,'raise',.5,.5)])
        batch.export(cls.fixture.summary_path, cls.fixture.video,
                     cls.fixture.batch_path, cls.fixture.out)

    @classmethod
    def tearDownClass(cls):
        cls.fixture.doCleanups()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name) / 'out'
        shutil.copytree(self.fixture.out, self.folder)

    def modify(self, name, key, value):
        path = self.folder / name
        data = json.loads(path.read_text())
        data[key] = value
        path.write_text(json.dumps(data))

    def test_two_clips_and_local_links(self):
        html = overview.overview(self.folder).read_text()
        self.assertIn('Clipes: 2', html)
        self.assertIn('clip-0.mp4', html)
        self.assertIn('clip-1.json', html)
        self.assertIn('não verificados', html)

    def test_refuses_overwrite(self):
        (self.folder / 'session_overview.html').write_text('keep')
        with self.assertRaisesRegex(ValueError, 'exists'):
            overview.overview(self.folder)
        self.assertEqual((self.folder / 'session_overview.html').read_text(), 'keep')

    def test_tampered_video(self):
        (self.folder / 'clip-0.mp4').write_bytes(b'corrupted')
        with self.assertRaisesRegex(ValueError, 'provenance'):
            overview.overview(self.folder)

    def test_tampered_provenance(self):
        self.modify('clip-0.json', 'source_video_sha256', '0'*64)
        with self.assertRaisesRegex(ValueError, 'provenance'):
            overview.overview(self.folder)

    def test_unsafe_filename(self):
        data = json.loads((self.folder / 'batch_report.json').read_text())
        data['clips'][0]['clip_filename'] = '../outside.mp4'
        self.modify('batch_report.json', 'clips', data['clips'])
        with self.assertRaisesRegex(ValueError, 'unsafe filename'):
            overview.overview(self.folder)

    def test_duplicate_clip_id(self):
        data = json.loads((self.folder / 'batch_report.json').read_text())
        data['clips'][1]['clip_id'] = data['clips'][0]['clip_id']
        self.modify('batch_report.json', 'clips', data['clips'])
        with self.assertRaisesRegex(ValueError, 'unsafe clip ID'):
            overview.overview(self.folder)

    def test_no_ocr_promotion(self):
        self.modify('clip-0.json', 'automatic_ocr_math_authorization', True)
        with self.assertRaisesRegex(ValueError, 'provenance'):
            overview.overview(self.folder)

    def test_escapes_untrusted_identity(self):
        data = json.loads((self.folder / 'batch_report.json').read_text())
        data['clips'][0]['table_id'] = '<script>bad</script>'
        self.modify('batch_report.json', 'clips', data['clips'])
        with self.assertRaisesRegex(ValueError, 'provenance'):
            overview.overview(self.folder)


if __name__ == '__main__':
    unittest.main()
