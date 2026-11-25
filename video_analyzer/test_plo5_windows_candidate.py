import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from plo5_windows_candidate import recover, audit, check
from plo5_session_load import fixture


class CandidateTests(unittest.TestCase):
    def test_recover_existing_media_without_redecode(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=fixture(root,8);out=root/'audit'
            first=audit(source,root/'regions.json',out,pixel_checks=4)
            with patch('plo5_windows_candidate.run',side_effect=AssertionError('Must not ingest again')):
                result=recover(out/'jobs.db',first['job_id'],120,root/'recovered')
            self.assertEqual(result['samples_pts_hash_audited'],12)
            self.assertFalse(result['real_session_validated'])
            a=json.loads((root/'recovered/annotations.json').read_text());self.assertTrue(all(x['truth']=={} for x in a['annotations']))
            with self.assertRaises(ValueError):recover(out/'jobs.db',first['job_id'],120,root/'recovered')
            with self.assertRaises(ValueError):recover(root/'missing.db',first['job_id'],120,root/'wrong')
            self.assertFalse((root/'wrong').exists())
            next((out/'evidence').rglob('*.jpg')).write_bytes(b'bad')
            with self.assertRaises(ValueError):recover(out/'jobs.db',first['job_id'],120,root/'tampered')
            self.assertFalse((root/'tampered').exists())

    def test_preflight_rejects_before_ingest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=fixture(root,8);out=root/'audit'
            with patch('plo5_windows_candidate.run',side_effect=AssertionError('No ingest')):
                for kw in ({'interval':0},{'pixel_checks':0},{'interval':float('nan')}):
                    with self.assertRaises(ValueError):audit(source,root/'regions.json',out,**kw)
                with patch('plo5_windows_candidate.shutil.disk_usage',return_value=type('Disk',(),{'free':0})()):
                    with self.assertRaisesRegex(ValueError,'disk'):audit(source,root/'regions.json',out)
            self.assertFalse(out.exists())

    def test_wrong_snapshot_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'wrong.sqlite';p.write_bytes(b'wrong')
            with self.assertRaises(ValueError):check(p)


if __name__=='__main__':unittest.main()
