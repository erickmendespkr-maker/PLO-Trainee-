"""Synthetic integration tests for the offline Poker Cortes handoff."""
import csv
import json
import tempfile
import unittest
from pathlib import Path

try:
    from .poker_cortes_pipeline import prepare_review_queue, save_review_queue
except ImportError:
    from poker_cortes_pipeline import prepare_review_queue, save_review_queue

SHA = 'a' * 64
FIELDS = ['inicio', 'fim', 'mesa', 'status', 'perda_bb', 'pote_confirmado', 'rebuy_visto']


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.csv = self.root / 'report.csv'

    def report(self, rows):
        with self.csv.open('w', encoding='utf-8', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS, delimiter=';')
            writer.writeheader()
            writer.writerows(rows)

    def row(self, **kw):
        row = dict(inicio='00:00:02', fim='00:00:12', mesa='1', status='PERDA',
                   perda_bb='320', pote_confirmado='SIM', rebuy_visto='NAO')
        row.update(kw)
        return row

    def queue(self):
        return prepare_review_queue(self.csv, video_sha256=SHA, duration_seconds=60)

    def test_high_loss_still_unverified(self):
        self.report([self.row()])
        item = self.queue()['items'][0]
        self.assertEqual(item['review_priority'], 'HIGH')
        self.assertIsNone(item['confirmed_loss_bb'])
        self.assertFalse(item['math_analysis_authorized'])
        self.assertFalse(item['clip_loss_label_authorized'])

    def test_four_tables(self):
        self.report([self.row(mesa=str(i), inicio=f'00:00:0{i}') for i in range(1, 5)])
        self.assertEqual(self.queue()['total'], 4)

    def test_rebuy_flag(self):
        row = self.row()
        row['rebuy_visto'] = 'SIM'
        self.report([row])
        self.assertIn('REBUY_REQUIRES_SEPARATE_ACCOUNTING', self.queue()['items'][0]['flags'])

    def test_bad_timestamp_rejected(self):
        row = self.row()
        row['fim'] = '00:02:00'
        self.report([row])
        with self.assertRaises(ValueError):
            self.queue()

    def test_duplicate_rejected(self):
        self.report([self.row(), self.row()])
        with self.assertRaises(ValueError):
            self.queue()

    def test_atomic_no_overwrite(self):
        self.report([self.row()])
        target = self.root / 'queue.json'
        save_review_queue(self.queue(), target)
        old = target.read_bytes()
        with self.assertRaises(FileExistsError):
            save_review_queue({'items': []}, target)
        self.assertEqual(old, target.read_bytes())
        self.assertEqual(json.loads(old)['total'], 1)

    def test_no_parent_directory(self):
        with self.assertRaises(ValueError):
            save_review_queue({}, self.root / 'missing' / 'q.json')


if __name__ == '__main__':
    unittest.main()
