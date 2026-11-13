import json
import tempfile
import unittest
from pathlib import Path
from offline_review_registry import append_review, verify_ledger, validate_review

BASE = dict(source_sha256='a'*64, hand_id='h1', table_id=1, start_seconds=1.0, end_seconds=2.0, review_status='insufficient_data')

class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'reviews.jsonl'

    def test_append_and_chain(self):
        append_review(self.path, BASE)
        append_review(self.path, {**BASE, 'hand_id': 'h2'})
        rows = verify_ledger(self.path)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1]['previous_sha256'], rows[0]['entry_sha256'])

    def test_modified_review_rejected(self):
        append_review(self.path, BASE)
        row = json.loads(self.path.read_text())
        row['review']['review_status'] = 'confirmed'
        self.path.write_text(json.dumps(row)+'\n')
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            verify_ledger(self.path)

    def test_truncated_chain_rejected(self):
        append_review(self.path, BASE)
        append_review(self.path, {**BASE, 'hand_id': 'h2'})
        lines = self.path.read_text().splitlines()
        self.path.write_text(lines[1]+'\n')
        with self.assertRaisesRegex(ValueError, 'broken ledger chain'):
            verify_ledger(self.path)

    def test_invalid_fields(self):
        for change in ({'table_id': True}, {'end_seconds': float('nan')}, {'review_status': 'gto'}, {'hand_id': '../evil'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_review({**BASE, **change})

    def test_symlink_rejected(self):
        target = Path(self.tmp.name) / 'target'
        target.write_text('')
        self.path.symlink_to(target)
        with self.assertRaises(ValueError):
            append_review(self.path, BASE)

if __name__ == '__main__':
    unittest.main()
