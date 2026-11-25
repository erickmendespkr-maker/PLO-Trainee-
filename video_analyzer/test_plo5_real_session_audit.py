import json
from pathlib import Path
import tempfile
import unittest

from plo5_session_load import fixture
from plo5_real_session_audit import run, summarize


class RecordedAuditTests(unittest.TestCase):
    def test_audit_and_blank_annotations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=fixture(root,8);out=root/'audit'
            r=run(source,root/'regions.json',out,pixel_checks=4)
            self.assertEqual((r['source_decoded_frames'],r['table_regions_declared'],r['scheduled_samples'],r['samples_pts_hash_audited'],r['pixel_spotchecks']),(8,4,12,12,4))
            self.assertEqual(r['samples_by_table'],{1:3,2:3,3:3,4:3});self.assertFalse(r['real_session_validated']);self.assertFalse(r['ocr_verified'])
            a=json.loads((out/'annotations.json').read_text());self.assertFalse(a['independent_review']);self.assertEqual(len(a['annotations']),12);self.assertTrue(all(x['truth']=={} for x in a['annotations']))
            with self.assertRaises(ValueError):run(source,root/'regions.json',out)
            crop=next((out/'evidence').rglob('*.jpg'));crop.write_bytes(b'tampered')
            with self.assertRaises(ValueError):summarize(out/'jobs.db',r['job_id'],120)


if __name__=='__main__':unittest.main()
