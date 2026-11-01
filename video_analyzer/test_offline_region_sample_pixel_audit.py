"""Synthetic FFmpeg replay and adversarial pixel-provenance tests."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from PIL import Image, ImageDraw

from offline_region_sample_pixel_audit import run, frame_index, frame_pts


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def media(*argv):
    subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True,
                   timeout=60, check=True)


def write(path, data):
    Path(path).write_text(json.dumps(data), encoding='utf-8')


class RegionPixelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.bundle = cls.root / 'bundle'
        (cls.bundle / 'frames').mkdir(parents=True)
        (cls.bundle / 'tables').mkdir()
        cls.video = cls.root / 'synthetic.mp4'
        still = cls.root / 'still.png'
        image = Image.new('RGB', (640, 360), 'white')
        d = ImageDraw.Draw(image)
        for table in range(4):
            x, y = table % 2 * 320, table // 2 * 180
            d.rectangle((x+15, y+20, x+210, y+130),
                        fill=('red', 'green', 'blue', 'yellow')[table])
        image.save(still)
        media('ffmpeg', '-v', 'error', '-nostdin', '-loop', '1', '-i', str(still),
              '-t', '2', '-r', '2', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
              str(cls.video))
        frame = cls.bundle / 'frames/frame_00.png'
        media('ffmpeg', '-v', 'error', '-nostdin', '-i', str(cls.video),
              '-frames:v', '1', '-update', '1', str(frame))
        regions, crops = [], []
        for table in range(1, 5):
            x, y = (table-1) % 2 * 320, (table-1) // 2 * 180
            crop = cls.bundle / f'tables/table_{table:02d}_sample_00.png'
            media('ffmpeg', '-v', 'error', '-nostdin', '-i', str(frame),
                  '-vf', f'crop=320:180:{x}:{y}', '-frames:v', '1',
                  '-update', '1', str(crop))
            regions.append({'table_id': table, 'x': x, 'y': y,
                            'width': 320, 'height': 180})
            crops.append({'table_id': table, 'path': crop.relative_to(cls.bundle).as_posix(),
                          'sha256': sha(crop), 'width': 320, 'height': 180})
        cls.manifest = {'schema_version': 1,
                        'analysis_status': 'unverified_four_table_region_samples_for_manual_review_only',
                        'recording_sha256': sha(cls.video),
                        'recording_duration_seconds': 2.0,
                        'frame_width': 640, 'frame_height': 360,
                        'regions': regions,
                        'samples': [{'requested_seek_seconds': 0.0,
                                     'decoded_source_pts_seconds': 0.0,
                                     'frame_path': 'frames/frame_00.png',
                                     'frame_sha256': sha(frame),
                                     'table_crops': crops}],
                        'timestamp_semantics': 'decoded_source_pts_seconds_from_ffmpeg_showinfo',
                        'regions_human_confirmed': False,
                        'cards_actions_verified': False,
                        'hand_boundaries_verified': False,
                        'ready_for_equity_or_ev': False,
                        'automatic_clip_selection_authorized': False}
        write(cls.bundle / 'region_samples.json', cls.manifest)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=self.root)
        self.addCleanup(self.temp.cleanup)
        self.out = Path(self.temp.name) / 'report.json'

    def execute(self):
        return run(self.video, self.bundle, self.out)

    def test_four_crops_match_independent_video_decode(self):
        result = self.execute()
        self.assertEqual(result['table_crops_verified'], 4)
        self.assertEqual(result['source_frames_independently_decoded'], 1)
        self.assertFalse(result['ready_for_equity_or_ev'])
        self.assertTrue(self.out.exists())

    def test_create_only(self):
        self.execute()
        with self.assertRaises(ValueError): self.execute()

    def test_changed_video_bytes_rejected(self):
        other = self.out.parent / 'other.mp4'
        other.write_bytes(self.video.read_bytes() + b'junk')
        with self.assertRaises(ValueError):
            run(other, self.bundle, self.out)
        self.assertFalse(self.out.exists())

    def test_crop_swap_and_rehash_rejected(self):
        target = self.bundle / 'tables/table_01_sample_00.png'
        source = self.bundle / 'tables/table_02_sample_00.png'
        manifest_path = self.bundle / 'region_samples.json'
        old_image, old_manifest = target.read_bytes(), manifest_path.read_bytes()
        try:
            target.write_bytes(source.read_bytes())
            changed = copy.deepcopy(self.manifest)
            changed['samples'][0]['table_crops'][0]['sha256'] = sha(target)
            write(manifest_path, changed)
            with self.assertRaisesRegex(ValueError, 'crop pixels'):
                self.execute()
            self.assertFalse(self.out.exists())
        finally:
            target.write_bytes(old_image)
            manifest_path.write_bytes(old_manifest)

    def test_source_frame_replacement_and_rehash_rejected(self):
        target = self.bundle / 'frames/frame_00.png'
        manifest_path = self.bundle / 'region_samples.json'
        old_image, old_manifest = target.read_bytes(), manifest_path.read_bytes()
        try:
            with Image.open(target) as img:
                altered = img.convert('RGB')
            altered.putpixel((0, 0), (5, 5, 5))
            altered.save(target)
            changed = copy.deepcopy(self.manifest)
            changed['samples'][0]['frame_sha256'] = sha(target)
            write(manifest_path, changed)
            with self.assertRaisesRegex(ValueError, 'source frame pixels'):
                self.execute()
        finally:
            target.write_bytes(old_image)
            manifest_path.write_bytes(old_manifest)

    def test_unmatched_pts_rejected(self):
        path = self.bundle / 'region_samples.json'
        original = path.read_bytes()
        try:
            changed = copy.deepcopy(self.manifest)
            changed['samples'][0]['decoded_source_pts_seconds'] = 0.25
            write(path, changed)
            with self.assertRaisesRegex(ValueError, 'source PTS not found'):
                self.execute()
        finally:
            path.write_bytes(original)

    def test_unsafe_promotion_rejected(self):
        path = self.bundle / 'region_samples.json'
        original = path.read_bytes()
        try:
            changed = copy.deepcopy(self.manifest)
            changed['ready_for_equity_or_ev'] = True
            write(path, changed)
            with self.assertRaises(ValueError): self.execute()
        finally:
            path.write_bytes(original)

    def test_symlink_output_rejected(self):
        self.out.symlink_to(self.bundle / 'region_samples.json')
        with self.assertRaises(ValueError): self.execute()

    def test_no_ffmpeg_rejected(self):
        with self.assertRaises(ValueError):
            run(self.video, self.bundle, self.out, ffmpeg='missing_ffmpeg_plo')
        self.assertFalse(self.out.exists())

    def test_frame_index_exact_and_ambiguous(self):
        self.assertEqual(frame_index([1.0, 1.5, 2.0], 1.500001), 1)
        with self.assertRaises(ValueError): frame_index([1.0, 1.5], 1.25)

    def test_real_ffprobe_timeline(self):
        pts = frame_pts(self.video)
        self.assertEqual(len(pts), 4)
        self.assertEqual(pts[0], 0)


if __name__ == '__main__':
    unittest.main()
