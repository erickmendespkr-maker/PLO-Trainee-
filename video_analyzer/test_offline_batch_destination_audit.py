import tempfile
import unittest
from pathlib import Path
from offline_batch_destination_audit import audit_destinations


class DestinationAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def plan(self, *paths):
        return [{'status': 'PLANNED_ONLY', 'destination': str(p)} for p in paths]

    def test_valid(self):
        result = audit_destinations(self.plan(self.root / 'a.mp4'), self.root)
        self.assertEqual(result[0]['status'], 'DESTINATION_AUDITED_NOT_RESERVED')

    def test_alias_duplicate(self):
        with self.assertRaises(ValueError):
            audit_destinations(self.plan(self.root / 'a.mp4', self.root / '.' / 'a.mp4'), self.root)

    def test_escape(self):
        with self.assertRaises(ValueError):
            audit_destinations(self.plan(self.root / '..' / 'outside.mp4'), self.root)

    def test_existing_manifest(self):
        (self.root / 'a.json').write_text('{}')
        with self.assertRaises(FileExistsError):
            audit_destinations(self.plan(self.root / 'a.mp4'), self.root)

    def test_symlink(self):
        (self.root / 'alias.mp4').symlink_to(self.root / 'missing.mp4')
        with self.assertRaises(ValueError):
            audit_destinations(self.plan(self.root / 'alias.mp4'), self.root)

    def test_directory_symlink_escape(self):
        other = self.root.parent
        (self.root / 'link').symlink_to(other, target_is_directory=True)
        with self.assertRaises(ValueError):
            audit_destinations(self.plan(self.root / 'link' / 'x.mp4'), self.root)

    def test_missing_parent(self):
        with self.assertRaises(ValueError):
            audit_destinations(self.plan(self.root / 'missing' / 'x.mp4'), self.root)

    def test_invalid_status(self):
        with self.assertRaises(ValueError):
            audit_destinations([{'status': 'APPROVED', 'destination': str(self.root / 'a.mp4')}], self.root)

    def test_empty(self):
        self.assertEqual(audit_destinations([], self.root), [])


if __name__ == '__main__':
    unittest.main()
