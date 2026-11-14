"""Synthetic integration checks for offline evidence-review composition."""
import json
import tempfile
import unittest
from pathlib import Path
from offline_evidence_review_pipeline import build_review_bundle, write_review_bundle


def fixture():
    return {'status': 'TECHNICAL_FRAME_EVIDENCE_ONLY',
            'source_absolute_pts_verified': False, 'ocr_verified': False,
            'hands_verified': False, 'equity_ev_verified': False,
            'tables': [{'table_id': tid, 'status': 'UNREVIEWED_FRAME_EVIDENCE',
                        'decoded_frame_count': 5,
                        'samples': [{'frame_index': i, 'crop_pts_seconds': float(i),
                                     'rgb_sha256': (str(tid) if i == 0 else 'a') * 64}
                                    for i in range(3)]} for tid in range(1, 5)]}


class TestPipeline(unittest.TestCase):
    def test_four_tables(self):
        result = build_review_bundle(fixture(), crop_start_seconds=30)
        self.assertEqual(len(result['timeline']['events']), 12)
        self.assertEqual(len(result['review_queue']['proposals']), 4)
        self.assertFalse(result['hands_verified'])
        self.assertFalse(result['source_identity_verified'])
        self.assertEqual(result['timeline']['events'][0]['nominal_source_seconds'], 30)

    def test_deterministic(self):
        self.assertEqual(build_review_bundle(fixture()), build_review_bundle(fixture()))

    def test_no_change(self):
        data = fixture()
        for t in data['tables']:
            for sample in t['samples']:
                sample['rgb_sha256'] = 'f' * 64
        self.assertEqual(build_review_bundle(data)['review_queue']['proposals'], [])

    def test_reject_verified(self):
        data = fixture()
        data['hands_verified'] = True
        with self.assertRaises(ValueError):
            build_review_bundle(data)

    def test_reject_bad_timestamp(self):
        data = fixture()
        data['tables'][0]['samples'][1]['crop_pts_seconds'] = -1
        with self.assertRaises(ValueError):
            build_review_bundle(data)

    def test_reject_duplicate_table(self):
        data = fixture()
        data['tables'][1]['table_id'] = 1
        with self.assertRaises(ValueError):
            build_review_bundle(data)

    def test_file_roundtrip_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            source, dest = Path(td)/'input.json', Path(td)/'out.json'
            source.write_text(json.dumps(fixture()))
            result = write_review_bundle(source, dest)
            self.assertEqual(json.loads(dest.read_text()), result)
            with self.assertRaises(FileExistsError):
                write_review_bundle(source, dest)

    def test_reject_same_path(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td)/'input.json'
            source.write_text(json.dumps(fixture()))
            with self.assertRaises(ValueError):
                write_review_bundle(source, source)

    def test_reject_symlink(self):
        with tempfile.TemporaryDirectory() as td:
            source, link, dest = Path(td)/'input.json', Path(td)/'link.json', Path(td)/'out.json'
            source.write_text(json.dumps(fixture()))
            link.symlink_to(source)
            with self.assertRaises(ValueError):
                write_review_bundle(link, dest)

    def test_invalid_gap(self):
        with self.assertRaises(ValueError):
            build_review_bundle(fixture(), min_gap_seconds=5, max_gap_seconds=1)


if __name__ == '__main__':
    unittest.main()
