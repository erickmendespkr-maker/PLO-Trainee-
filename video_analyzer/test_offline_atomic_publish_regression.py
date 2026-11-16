"""Independent filesystem regressions for offline pair publication."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from offline_atomic_artifact_publish import publish_pair_no_clobber

class PublishPairRegressionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.video = self.root / 'stage.mp4'
        self.json = self.root / 'stage.json'
        self.final_video = self.root / 'clip.mp4'
        self.final_json = self.root / 'clip.mp4.json'
        self.video.write_bytes(b'video')
        self.json.write_bytes(b'{"ok":true}')

    def publish(self):
        return publish_pair_no_clobber(self.video, self.json, self.final_video, self.final_json)

    def test_successful_pair_preserves_contents(self):
        self.publish()
        self.assertEqual(self.final_video.read_bytes(), b'video')
        self.assertEqual(self.final_json.read_bytes(), b'{"ok":true}')

    def test_existing_json_does_not_publish_video(self):
        self.final_json.write_bytes(b'competitor')
        with self.assertRaises(FileExistsError): self.publish()
        self.assertFalse(self.final_video.exists())
        self.assertEqual(self.final_json.read_bytes(), b'competitor')

    def test_conflict_on_second_link_rolls_back_only_own_video(self):
        actual = os.link
        def collide(src, dst, **kwargs):
            if Path(dst) == self.final_json:
                self.final_json.write_bytes(b'competitor')
                raise FileExistsError('simulated race')
            return actual(src, dst, **kwargs)
        with patch('offline_atomic_artifact_publish.os.link', side_effect=collide):
            with self.assertRaises(FileExistsError): self.publish()
        self.assertFalse(self.final_video.exists())
        self.assertEqual(self.final_json.read_bytes(), b'competitor')

    def test_empty_stage_rejected(self):
        self.json.write_bytes(b'')
        with self.assertRaises(ValueError): self.publish()
        self.assertFalse(self.final_video.exists())

    def test_existing_video_preserved(self):
        self.final_video.write_bytes(b'competitor')
        with self.assertRaises(FileExistsError): self.publish()
        self.assertEqual(self.final_video.read_bytes(), b'competitor')
        self.assertFalse(self.final_json.exists())

if __name__ == '__main__': unittest.main()
