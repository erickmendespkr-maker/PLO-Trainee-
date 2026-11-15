import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from offline_atomic_artifact_publish import publish_pair_no_clobber

class AtomicPublishTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.a, self.b = root/'stage.mp4', root/'stage.json'
        self.x, self.y = root/'clip.mp4', root/'clip.json'
        self.a.write_bytes(b'video')
        self.b.write_bytes(b'{"ok":false}')

    def publish(self):
        return publish_pair_no_clobber(self.a, self.b, self.x, self.y)

    def test_success(self):
        self.publish()
        self.assertEqual(self.x.read_bytes(), b'video')
        self.assertEqual(self.y.read_bytes(), b'{"ok":false}')

    def test_existing_video_preserved(self):
        self.x.write_bytes(b'other')
        with self.assertRaises(FileExistsError): self.publish()
        self.assertEqual(self.x.read_bytes(), b'other')

    def test_existing_json_preserved(self):
        self.y.write_bytes(b'other')
        with self.assertRaises(FileExistsError): self.publish()
        self.assertFalse(self.x.exists())
        self.assertEqual(self.y.read_bytes(), b'other')

    def test_second_link_race_rollback(self):
        original = os.link
        def collide(src, dst, **kw):
            if Path(dst) == self.y:
                self.y.write_bytes(b'competitor')
                raise FileExistsError('race')
            return original(src, dst, **kw)
        with patch('offline_atomic_artifact_publish.os.link', side_effect=collide):
            with self.assertRaises(FileExistsError): self.publish()
        self.assertFalse(self.x.exists())
        self.assertEqual(self.y.read_bytes(), b'competitor')

    def test_missing_staged(self):
        self.a.unlink()
        with self.assertRaises(ValueError): self.publish()

    def test_empty_staged(self):
        self.b.write_bytes(b'')
        with self.assertRaises(ValueError): self.publish()

    def test_symlink_staged_rejected(self):
        self.a.unlink()
        self.a.symlink_to(self.b)
        with self.assertRaises(ValueError): self.publish()

    def test_alias_paths_rejected(self):
        with self.assertRaises(ValueError):
            publish_pair_no_clobber(self.a, self.b, self.a, self.y)

    def test_second_attempt_rejected(self):
        self.publish()
        with self.assertRaises(FileExistsError): self.publish()

if __name__ == '__main__': unittest.main()
