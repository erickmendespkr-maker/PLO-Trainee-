import copy
import json
import tempfile
import unittest
from pathlib import Path
from offline_evidence_timeline import build_timeline, write_timeline


def fixture():
    return {'status': 'TECHNICAL_FRAME_EVIDENCE_ONLY',
            'source_absolute_pts_verified': False, 'ocr_verified': False,
            'hands_verified': False, 'equity_ev_verified': False,
            'tables': [{'table_id': 1, 'decoded_frame_count': 20,
                        'status': 'UNREVIEWED_FRAME_EVIDENCE', 'samples': [
                            {'frame_index': 0, 'crop_pts_seconds': 0.0, 'rgb_sha256': 'a'*64},
                            {'frame_index': 10, 'crop_pts_seconds': 1.0, 'rgb_sha256': 'b'*64}]}]}

class TimelineTests(unittest.TestCase):
    def test_timeline(self):
        result = build_timeline(fixture(), crop_start_seconds=120)
        self.assertEqual(result['events'][1]['nominal_source_seconds'], 121)
        self.assertFalse(result['events'][1]['nominal_source_seconds_verified'])
    def test_deterministic(self):
        self.assertEqual(build_timeline(fixture()), build_timeline(fixture()))
    def test_four_tables(self):
        f=fixture(); f['tables']=[dict(copy.deepcopy(f['tables'][0]), table_id=i) for i in range(1,5)]
        self.assertEqual(len(build_timeline(f)['events']),8)
    def test_reject_claims(self):
        for key in ('hands_verified','ocr_verified','equity_ev_verified','source_absolute_pts_verified'):
            f=fixture(); f[key]=True
            with self.subTest(key=key), self.assertRaises(ValueError): build_timeline(f)
    def test_reject_duplicate_id(self):
        f=fixture(); f['tables']*=2
        with self.assertRaises(ValueError): build_timeline(f)
    def test_reject_invalid_hash(self):
        f=fixture(); f['tables'][0]['samples'][0]['rgb_sha256']='g'*64
        with self.assertRaises(ValueError): build_timeline(f)
    def test_reject_bad_order(self):
        f=fixture(); f['tables'][0]['samples'][1]['crop_pts_seconds']=0
        with self.assertRaises(ValueError): build_timeline(f)
    def test_reject_bool_index(self):
        f=fixture(); f['tables'][0]['samples'][0]['frame_index']=False
        with self.assertRaises(ValueError): build_timeline(f)
    def test_reject_bad_offset(self):
        for offset in (-1,float('nan'),True):
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                build_timeline(fixture(),crop_start_seconds=offset)
    def test_file_write_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'evidence.json'; target=Path(d)/'timeline.json'
            source.write_text(json.dumps(fixture()))
            write_timeline(source,target)
            self.assertEqual(json.loads(target.read_text())['status'],'UNREVIEWED_TIMELINE')
            with self.assertRaises(FileExistsError): write_timeline(source,target)

if __name__=='__main__': unittest.main()
