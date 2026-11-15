"""Synthetic regression for provisional batch preparation."""
import tempfile
import unittest
from pathlib import Path
try:
    from .offline_batch_ready import prepare_batch
except ImportError:
    from offline_batch_ready import prepare_batch

FLAGS = ('table_verified', 'hand_verified', 'hero_cards_verified',
         'board_verified', 'action_verified', 'amounts_verified')

class BatchReadyTests(unittest.TestCase):
    def item(self, root, name='a.mp4', table=1, start=1, end=3):
        return {'destination': str(root / name), 'status': 'PLANNED_ONLY',
                'human_review_required': True,
                'record': {'table_id': table, 'start_pts': start, 'end_pts': end,
                           **{k: False for k in FLAGS}}}

    def test_valid_two_tables(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            result = prepare_batch([self.item(root), self.item(root, 'b.mp4', 4, 3, 5)], 10, root)
            self.assertEqual(result['total_seconds'], 4)
            self.assertEqual(len(result['clips']), 2)
            self.assertTrue(all(x['human_review_required'] for x in result['clips']))
            self.assertFalse(list(root.iterdir()))

    def test_alias_collision(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            with self.assertRaises(ValueError):
                prepare_batch([self.item(root), self.item(root, './a.mp4')], 10, root)

    def test_outside_root(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as other:
            with self.assertRaises(ValueError):
                prepare_batch([self.item(Path(other))], 10, Path(d))

    def test_existing_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'a.json').write_text('{}')
            with self.assertRaises(FileExistsError):
                prepare_batch([self.item(root)], 10, root)

    def test_verified_evidence_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            item = self.item(root)
            item['record']['hand_verified'] = True
            with self.assertRaises(ValueError):
                prepare_batch([item], 10, root)

    def test_budget_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            with self.assertRaises(ValueError):
                prepare_batch([self.item(root)], 10, root, max_total_seconds=1)

    def test_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'a.mp4').symlink_to(root / 'missing.mp4')
            with self.assertRaises(ValueError):
                prepare_batch([self.item(root)], 10, root)

if __name__ == '__main__':
    unittest.main()
