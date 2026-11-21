"""End-to-end synthetic regression for CSV -> bridge -> four-table review."""
import csv
import hashlib
import tempfile
import unittest
from pathlib import Path

try:
    from .poker_cortes_evidence_bridge import build_evidence_review, write_review_json
except ImportError:
    from poker_cortes_evidence_bridge import build_evidence_review, write_review_json

VIDEO = hashlib.sha256(b'synthetic-video').hexdigest()
FIELDS = ['inicio', 'fim', 'mesa', 'status', 'perda_bb', 'rebuy_visto']


class CsvBridgeIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.csv = Path(self.tmp.name) / 'hands.csv'
        with self.csv.open('w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS, delimiter=';')
            writer.writeheader()
            for table in range(1, 5):
                writer.writerow(dict(inicio='00:00:01', fim='00:00:10', mesa=table,
                                     status='CONFIRMADO', perda_bb='300', rebuy_visto='SIM' if table == 2 else ''))
    def obs(self, table, t, value):
        return dict(table_id=table, video_sha256=VIDEO, time_seconds=t,
                    stack_bb=value, source_frame=f't{table}-{t}')

    def test_all_four_tables_and_rebuy(self):
        result = build_evidence_review(self.csv,
            [self.obs(1, 2, 350), self.obs(1, 9, 1), self.obs(2, 5, 100)],
            video_sha256=VIDEO, duration_seconds=20)
        self.assertEqual(len(result['hands']), 4)
        self.assertEqual(len(result['hands'][0]['stack_samples']), 2)
        self.assertIn('LARGE_STACK_JUMP_RECHECK_OCR', result['hands'][0]['flags'])
        self.assertIn('REBUY_REQUIRES_RECONCILIATION', result['hands'][1]['flags'])
        self.assertTrue(all(h['confirmed_loss_bb'] is None for h in result['hands']))
        self.assertFalse(result['ev_authorized'])
        self.assertFalse(result['mp4_loss_label_authorized'])

    def test_output_cannot_overwrite(self):
        result = build_evidence_review(self.csv, [], video_sha256=VIDEO, duration_seconds=20)
        target = Path(self.tmp.name) / 'review.json'
        write_review_json(result, target)
        with self.assertRaises(FileExistsError):
            write_review_json(result, target)

    def test_unmatched_observation_stays_unresolved(self):
        result = build_evidence_review(self.csv, [self.obs(1, 15, 99)],
                                       video_sha256=VIDEO, duration_seconds=20)
        self.assertEqual(result['unresolved_observations'][0]['reason'], 'NO_MATCHING_HAND')


if __name__ == '__main__':
    unittest.main()
