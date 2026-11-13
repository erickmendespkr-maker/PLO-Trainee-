import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from offline_review_registry import append_review
from offline_ledger_binding import audit_against_ledger

BASE = dict(source_sha256='a'*64, hand_id='h1', table_id=1,
            start_seconds=1.0, end_seconds=2.0, review_status='insufficient_data')

class LedgerBindingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.ledger = Path(self.temp.name) / 'ledger.jsonl'

    @patch('offline_ledger_binding.audit_against_review', return_value={'ok': True})
    def test_latest_review_selected(self, audit):
        append_review(self.ledger, BASE)
        latest = append_review(self.ledger, {**BASE, 'review_status': 'confirmed'})
        result = audit_against_ledger('clip.mp4', self.ledger, hand_id='h1', table_id=1, source_sha256='a'*64,
                                      expected_head_sha256=latest['entry_sha256'])
        self.assertEqual(audit.call_args.args[1]['review_status'], 'confirmed')
        self.assertEqual(result['ledger_sequence'], 2)
        self.assertFalse(result['visual_hand_verified'])

    def test_missing_match_fails(self):
        append_review(self.ledger, BASE)
        with self.assertRaisesRegex(ValueError, 'no matching'):
            audit_against_ledger('clip.mp4', self.ledger, hand_id='other', table_id=1, source_sha256='a'*64)

    def test_head_checkpoint_detects_rollback(self):
        append_review(self.ledger, BASE)
        last = append_review(self.ledger, {**BASE, 'hand_id': 'h2'})
        self.ledger.write_text(self.ledger.read_text().splitlines()[0]+'\n')
        with self.assertRaisesRegex(ValueError, 'checkpoint mismatch'):
            audit_against_ledger('clip.mp4', self.ledger, hand_id='h1', table_id=1, source_sha256='a'*64,
                                 expected_head_sha256=last['entry_sha256'])

    def test_tampering_detected(self):
        append_review(self.ledger, BASE)
        self.ledger.write_text(self.ledger.read_text().replace('insufficient_data', 'confirmed'))
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            audit_against_ledger('clip.mp4', self.ledger, hand_id='h1', table_id=1, source_sha256='a'*64)

    def test_empty_ledger_fails(self):
        self.ledger.write_text('')
        with self.assertRaisesRegex(ValueError, 'empty'):
            audit_against_ledger('clip.mp4', self.ledger, hand_id='h1', table_id=1, source_sha256='a'*64)

    @patch('offline_ledger_binding.audit_against_review', return_value={'ok': True})
    def test_superseded_table_review_rejected(self, audit):
        append_review(self.ledger, BASE)
        append_review(self.ledger, {**BASE, 'table_id': 2})
        with self.assertRaisesRegex(ValueError, 'latest hand review identity mismatch'):
            audit_against_ledger('clip.mp4', self.ledger, hand_id='h1', table_id=1, source_sha256='a'*64)
        audit.assert_not_called()

    @patch('offline_ledger_binding.audit_against_review', return_value={'ok': True})
    def test_superseded_source_review_rejected(self, audit):
        append_review(self.ledger, BASE)
        append_review(self.ledger, {**BASE, 'source_sha256': 'b'*64})
        with self.assertRaisesRegex(ValueError, 'latest hand review identity mismatch'):
            audit_against_ledger('clip.mp4', self.ledger, hand_id='h1', table_id=1, source_sha256='a'*64)
        audit.assert_not_called()

if __name__ == '__main__':
    unittest.main()
