"""Synthetic tests only: real video recognition accuracy is NOT measured."""
import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import subprocess

import offline_ffmpeg_tesseract_proposals as extractor
import offline_ocr_review_bridge as bridge
import offline_reviewed_hand_math_queue as queue


def sample_spec():
    samples = []
    for i in range(4):
        x = (i % 2) * 640 + 185
        y = (i // 2) * 360 + 125
        samples.append({'hand_id': f'H{i+1}', 'table_id': f'T{i+1}',
                        'field': 'hero_card', 'slot': 0, 'pts_seconds': 1,
                        'roi': {'x': x / 1280, 'y': y / 720,
                                'w': 200 / 1280, 'h': 130 / 720}})
    return {'schema_version': 1, 'status': 'human_declared_offline_roi_samples',
            'samples': samples}


class ExtractorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not shutil.which('ffmpeg') or not shutil.which('ffprobe') or not shutil.which('tesseract'):
            raise unittest.SkipTest('FFmpeg/ffprobe/Tesseract required for integration fixture')
        try:
            from PIL import Image, ImageDraw, ImageFont
            font = ImageFont.truetype('DejaVuSans-Bold.ttf', 68)
            small = ImageFont.truetype('DejaVuSans-Bold.ttf', 38)
        except (ImportError, OSError) as exc:
            raise unittest.SkipTest('Pillow and DejaVuSans-Bold required for synthetic fixture') from exc
        cls.root = tempfile.TemporaryDirectory()
        root = Path(cls.root.name)
        frame = Image.new('RGB', (1280, 720), 'white')
        draw = ImageDraw.Draw(frame)
        for i, card in enumerate(('As', 'Kd', 'Qh', 'Jc')):
            x, y = (i % 2) * 640, (i // 2) * 360
            draw.rectangle((x+12, y+12, x+625, y+340), outline='black', width=4)
            draw.text((x+30, y+35), f'TABLE {i+1}', font=small, fill='black')
            draw.text((x+200, y+145), card, font=font, fill='black')
        image_path = root / 'frame.png'
        frame.save(image_path)
        cls.video = root / 'synthetic_four_tables.mp4'
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
                        '-loop', '1', '-i', str(image_path), '-t', '3', '-r', '1',
                        '-c:v', 'mpeg4', '-q:v', '2', str(cls.video)],
                       check=True, capture_output=True, timeout=30)
        cls.plan = {'schema_version': 1,
                    'status': 'human_reviewed_clip_plan_not_automated_hand_detection',
                    'source_video_sha256': queue.digest(cls.video),
                    'equity_or_ev_calculated': False,
                    'clips': [{'hand_id': f'H{i+1}', 'table_id': f'T{i+1}',
                               'start_seconds': .5, 'end_seconds': 2.5,
                               'review_basis': 'human_declared_boundaries_not_automatic_detection'}
                              for i in range(4)]}
        cls.plan_path = root / 'plan.json'
        cls.plan_path.write_text(json.dumps(cls.plan))

    @classmethod
    def tearDownClass(cls):
        cls.root.cleanup()

    def test_real_ffmpeg_tesseract_four_synthetic_cards(self):
        observations, skipped, digest = extractor.build(self.video, self.plan, sample_spec())
        self.assertEqual([o['value'] for o in observations], ['As', 'Kd', 'Qh', 'Jc'])
        self.assertEqual(skipped, 0)
        self.assertEqual(digest, queue.digest(self.video))
        self.assertTrue(all(o['engine'] == 'tesseract' for o in observations))
        self.assertTrue(all(0 <= o['confidence'] <= 1 for o in observations))

    def test_unverified_math_queue_invariant(self):
        observations, _, digest = extractor.build(self.video, self.plan, sample_spec())
        proposals = {'schema_version': 1, 'status': 'offline_ocr_proposals_unverified',
                     'source_plan_sha256': queue.digest(self.plan_path),
                     'source_video_sha256_claim': digest, 'observations': observations}
        worksheet, annotations = bridge.build(self.plan, proposals, queue.digest(self.plan_path), '0'*64)
        self.assertEqual(len(worksheet['hands']), 4)
        self.assertFalse(worksheet['card_claims_verified'])
        result = queue.build(self.plan, annotations, queue.digest(self.plan_path), '0'*64)
        self.assertEqual(result['eligible_count'], 0)

    def test_cli_outputs_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            spec = root / 'spec.json'
            out = root / 'proposals.json'
            spec.write_text(json.dumps(sample_spec()))
            args = [str(self.video), str(self.plan_path), str(spec), str(out)]
            self.assertEqual(extractor.main(args), 0)
            self.assertEqual(len(queue.read(out)['observations']), 4)
            with self.assertRaisesRegex(ValueError, 'distinct new'):
                extractor.main(args)

    def test_plan_video_hash_rejected(self):
        plan = copy.deepcopy(self.plan)
        plan['source_video_sha256'] = 'f'*64
        with self.assertRaisesRegex(ValueError, 'SHA-256'):
            extractor.build(self.video, plan, sample_spec())

    def test_wrong_table_rejected(self):
        spec = sample_spec(); spec['samples'][0]['table_id'] = 'T2'
        with self.assertRaisesRegex(ValueError, 'cross-table'):
            extractor.build(self.video, self.plan, spec)

    def test_outside_hand_rejected(self):
        spec = sample_spec(); spec['samples'][0]['pts_seconds'] = 0
        with self.assertRaisesRegex(ValueError, 'timestamp'):
            extractor.build(self.video, self.plan, spec)

    def test_outside_video_rejected(self):
        spec = sample_spec(); spec['samples'][0]['pts_seconds'] = 3.0
        with self.assertRaisesRegex(ValueError, 'timestamp'):
            extractor.build(self.video, self.plan, spec)

    def test_bad_roi_rejected(self):
        spec = sample_spec(); spec['samples'][0]['roi']['x'] = .99
        with self.assertRaisesRegex(ValueError, 'ROI'):
            extractor.build(self.video, self.plan, spec)

    def test_tiny_roi_rejected(self):
        spec = sample_spec(); spec['samples'][0]['roi']['w'] = .001
        with self.assertRaisesRegex(ValueError, 'too small'):
            extractor.build(self.video, self.plan, spec)

    def test_duplicate_sample_rejected(self):
        spec = sample_spec(); spec['samples'].append(copy.deepcopy(spec['samples'][0]))
        with self.assertRaisesRegex(ValueError, 'duplicate OCR'):
            extractor.build(self.video, self.plan, spec)

    def test_bool_slot_rejected(self):
        spec = sample_spec(); spec['samples'][0]['slot'] = True
        with self.assertRaisesRegex(ValueError, 'slot'):
            extractor.build(self.video, self.plan, spec)

    def test_unsupported_field_rejected(self):
        spec = sample_spec(); spec['samples'][0]['field'] = 'hole_cards_hidden'
        with self.assertRaisesRegex(ValueError, 'field'):
            extractor.build(self.video, self.plan, spec)

    def test_too_many_samples_rejected(self):
        spec = sample_spec(); spec['samples'] *= 1501
        with self.assertRaisesRegex(ValueError, 'specification'):
            extractor.build(self.video, self.plan, spec)

    def test_empty_tesseract_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            # TSV fixture with only negative-confidence/no-text rows.
            from unittest.mock import patch
            from subprocess import CompletedProcess
            with patch.object(extractor, 'run', return_value=CompletedProcess([], 0, stdout='level\tconf\ttext\n5\t-1\t\n')):
                self.assertIsNone(extractor.ocr_image(Path(d) / 'fake.png'))

    def test_non_ascii_ocr_skipped(self):
        from unittest.mock import patch
        from subprocess import CompletedProcess
        with patch.object(extractor, 'run', return_value=CompletedProcess([], 0, stdout='level\tconf\ttext\n5\t90\tÁs\n')):
            self.assertIsNone(extractor.ocr_image('fake.png'))

    def test_confidence_conservative_minimum(self):
        from unittest.mock import patch
        from subprocess import CompletedProcess
        rows = 'level\tconf\ttext\n5\t98\tA\n5\t45\ts\n'
        with patch.object(extractor, 'run', return_value=CompletedProcess([], 0, stdout=rows)):
            self.assertEqual(extractor.ocr_image('fake.png'), ('A s', .45))

    def test_output_path_equal_input_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            spec = Path(d) / 'spec.json'; spec.write_text(json.dumps(sample_spec()))
            with self.assertRaisesRegex(ValueError, 'distinct new'):
                extractor.main([str(self.video), str(self.plan_path), str(spec), str(spec)])

    def test_symlink_video_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            symlink = Path(d) / 'fake.mp4'; symlink.symlink_to(self.video)
            with self.assertRaisesRegex(ValueError, 'invalid local video'):
                extractor.build(symlink, self.plan, sample_spec())


if __name__ == '__main__':
    unittest.main()
