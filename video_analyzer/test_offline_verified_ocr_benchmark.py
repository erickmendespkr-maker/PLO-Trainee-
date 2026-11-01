"""Real FFmpeg/Tesseract synthetic evidence tests for offline OCR provenance."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from PIL import Image, ImageDraw, ImageFont

from offline_verified_ocr_benchmark import run


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def cmd(*args):
    return subprocess.run(args, check=True, capture_output=True, timeout=45)


def write_json(path, obj):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False), encoding='utf-8')


class VerifiedOCRTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.bundle = cls.root / 'bundle'
        (cls.bundle / 'frames').mkdir(parents=True)
        (cls.bundle / 'tables').mkdir()
        cls.video = cls.root / 'recording.mp4'
        image = Image.new('RGB', (640, 360), 'white')
        painter = ImageDraw.Draw(image)
        font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 64)
        for table, number in enumerate(('12', '23', '34', '45'), 1):
            x = ((table-1) % 2) * 320
            y = ((table-1) // 2) * 180
            painter.text((x+50, y+40), number, fill='black', font=font)
        still = cls.root / 'source.png'
        image.save(still)
        cmd('ffmpeg', '-v', 'error', '-nostdin', '-loop', '1', '-i', str(still),
            '-t', '2', '-r', '2', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(cls.video))
        frame = cls.bundle / 'frames/frame_00.png'
        cmd('ffmpeg', '-v', 'error', '-nostdin', '-i', str(cls.video),
            '-frames:v', '1', '-update', '1', str(frame))
        cls.pts = 0.0
        crops = []
        regions = []
        cls.raw = []
        for table in range(1, 5):
            x, y = ((table-1) % 2) * 320, ((table-1) // 2) * 180
            crop = cls.bundle / f'tables/table_{table:02d}_sample_00.png'
            cmd('ffmpeg', '-v', 'error', '-nostdin', '-i', str(frame),
                '-vf', f'crop=320:180:{x}:{y}', '-frames:v', '1', '-update', '1', str(crop))
            crops.append({'table_id': table, 'path': crop.relative_to(cls.bundle).as_posix(),
                          'sha256': digest(crop), 'width': 320, 'height': 180})
            regions.append({'table_id': table, 'x': x, 'y': y, 'width': 320, 'height': 180})
            roi = cls.root / f'roi_{table}.png'
            cmd('ffmpeg', '-v', 'error', '-nostdin', '-i', str(crop),
                '-vf', 'crop=220:110:25:20', '-frames:v', '1', '-update', '1', str(roi))
            ocr = cmd('tesseract', str(roi), 'stdout', '--psm', '6', 'tsv').stdout.decode()
            # Use the real engine's TSV parser, not a mocked recognition result.
            from offline_four_table_ocr_proposals import _parse_tsv
            raw, count, confidence = _parse_tsv(ocr.encode())
            cls.raw.append((raw, count, confidence))
        cls.source = {
            'schema_version': 1,
            'analysis_status': 'unverified_four_table_region_samples_for_manual_review_only',
            'recording_sha256': digest(cls.video), 'layout_sha256': 'a'*64,
            'recording_duration_seconds': 2, 'frame_width': 640, 'frame_height': 360,
            'regions': regions,
            'samples': [{'requested_seek_seconds': 0.0, 'decoded_source_pts_seconds': cls.pts,
                         'seek_delta_seconds': 0.0, 'frame_path': 'frames/frame_00.png',
                         'frame_sha256': digest(frame), 'table_crops': crops}],
            'timestamp_semantics': 'decoded_source_pts_seconds_from_ffmpeg_showinfo',
            'regions_human_confirmed': False, 'cards_actions_verified': False,
            'hand_boundaries_verified': False, 'ready_for_equity_or_ev': False,
            'automatic_clip_selection_authorized': False}
        write_json(cls.bundle/'region_samples.json', cls.source)
        cls.ocr = {'schema_version': 1, 'analysis_status': 'unverified_four_table_ocr_proposals_only',
                   'ready_for_equity_or_ev': False, 'requires_manual_review': True,
                   'automatic_hand_or_action_inference': False,
                   'engine_confidence_is_calibrated_probability': False,
                   'recording_sha256': digest(cls.video),
                   'source_region_samples_sha256': digest(cls.bundle/'region_samples.json'),
                   'candidates': []}
        for table, (raw, count, conf) in enumerate(cls.raw, 1):
            cls.ocr['candidates'].append({
                'table_id': table, 'sample_index': 0, 'field': 'pot',
                'decoded_source_pts_seconds': cls.pts, 'status': 'needs_manual_review',
                'parsed_candidate': None, 'source_crop_sha256': crops[table-1]['sha256'],
                'source_crop_path': crops[table-1]['path'], 'raw_ocr_text': raw,
                'roi': {'x': 25, 'y': 20, 'width': 220, 'height': 110},
                'word_count': count,
                'tesseract_mean_word_confidence_uncalibrated': conf})
        cls.gold = [{'table_id': t, 'field': 'pot', 'timestamp': cls.pts,
                     'expected': float(n)}
                    for t, n in enumerate((12, 23, 34, 45), 1)]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=self.root)
        self.addCleanup(self.temp.cleanup)
        self.d = Path(self.temp.name)
        self.ocr_path = self.d/'ocr.json'
        self.gold_path = self.d/'gold.json'
        self.out = self.d/'report.json'
        write_json(self.ocr_path, self.ocr)
        write_json(self.gold_path, self.gold)

    def execute(self):
        return run(self.video, self.bundle, self.ocr_path, self.gold_path, self.out)

    def test_real_tesseract_ffmpeg_four_table_end_to_end(self):
        report = self.execute()
        self.assertEqual(report['summary']['labeled'], 4)
        self.assertEqual(report['source_crop_hashes_verified'], 4)
        self.assertFalse(report['ready_for_equity_or_ev'])
        self.assertFalse(report['real_video_ocr_accuracy_verified'])
        self.assertEqual(len(self.raw), 4)
        self.assertTrue(self.out.is_file())
        print('ACTUAL_TESSERACT_RAW', [x[0] for x in self.raw])
        print('SYNTHETIC_LABEL_AGREEMENT', report['summary'])

    def test_create_only(self):
        self.execute()
        with self.assertRaises(ValueError): self.execute()

    def test_video_bytes_tampered(self):
        video = self.d/'other.mp4'
        video.write_bytes(self.video.read_bytes()+b'\0')
        with self.assertRaises(ValueError):
            run(video, self.bundle, self.ocr_path, self.gold_path, self.out)
        self.assertFalse(self.out.exists())

    def test_ocr_recording_hash_wrong(self):
        obj = copy.deepcopy(self.ocr); obj['recording_sha256']='f'*64
        write_json(self.ocr_path, obj)
        with self.assertRaises(ValueError): self.execute()

    def test_source_manifest_hash_wrong(self):
        obj = copy.deepcopy(self.ocr); obj['source_region_samples_sha256']='f'*64
        write_json(self.ocr_path, obj)
        with self.assertRaises(ValueError): self.execute()

    def test_crop_path_swap_with_correct_declared_hash(self):
        obj = copy.deepcopy(self.ocr)
        obj['candidates'][0]['source_crop_path'] = obj['candidates'][1]['source_crop_path']
        obj['candidates'][0]['source_crop_sha256'] = obj['candidates'][1]['source_crop_sha256']
        write_json(self.ocr_path, obj)
        with self.assertRaises(ValueError): self.execute()

    def test_crop_pixels_tampered(self):
        original = self.bundle/'tables/table_01_sample_00.png'
        # Restore even when assertion fails, to avoid contaminating other tests.
        saved = original.read_bytes()
        try:
            original.write_bytes(saved+b'junk')
            with self.assertRaises(ValueError): self.execute()
        finally:
            original.write_bytes(saved)

    def test_bad_ocr_timestamp(self):
        obj = copy.deepcopy(self.ocr); obj['candidates'][0]['decoded_source_pts_seconds'] += 0.5
        write_json(self.ocr_path, obj)
        with self.assertRaises(ValueError): self.execute()

    def test_roi_outside_crop(self):
        obj = copy.deepcopy(self.ocr); obj['candidates'][0]['roi']['x'] = 200
        write_json(self.ocr_path, obj)
        with self.assertRaises(ValueError): self.execute()

    def test_gold_not_at_sample_time(self):
        obj = copy.deepcopy(self.gold); obj[0]['timestamp'] = 1.5
        write_json(self.gold_path, obj)
        with self.assertRaises(ValueError): self.execute()

    def test_promotion_rejected(self):
        obj = copy.deepcopy(self.ocr); obj['ready_for_equity_or_ev'] = True
        write_json(self.ocr_path, obj)
        with self.assertRaises(ValueError): self.execute()

    def test_duplicate_json_keys_rejected(self):
        self.ocr_path.write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaises(ValueError): self.execute()

    def test_symlink_ocr_rejected(self):
        link = self.d/'ocr_link.json'
        link.symlink_to(self.ocr_path)
        with self.assertRaises(ValueError):
            run(self.video, self.bundle, link, self.gold_path, self.out)

    def test_source_duration_mismatch(self):
        manifest = self.bundle/'region_samples.json'
        saved = manifest.read_bytes()
        try:
            source = copy.deepcopy(self.source)
            source['recording_duration_seconds'] = 999
            write_json(manifest, source)
            with self.assertRaises(ValueError): self.execute()
        finally:
            manifest.write_bytes(saved)

    def test_source_frame_hash_tampered(self):
        frame = self.bundle/'frames/frame_00.png'
        saved = frame.read_bytes()
        try:
            frame.write_bytes(saved+b'tamper')
            with self.assertRaises(ValueError): self.execute()
        finally:
            frame.write_bytes(saved)

    def test_cross_table_label_timestamp_rejected(self):
        obj = copy.deepcopy(self.gold)
        obj[0]['table_id'] = 5
        write_json(self.gold_path, obj)
        with self.assertRaises(ValueError): self.execute()

    def test_bad_source_safety_flag(self):
        manifest = self.bundle/'region_samples.json'
        saved = manifest.read_bytes()
        try:
            source = copy.deepcopy(self.source)
            source['ready_for_equity_or_ev'] = True
            write_json(manifest, source)
            with self.assertRaises(ValueError): self.execute()
        finally:
            manifest.write_bytes(saved)

    def test_source_manifest_schema_bool_rejected(self):
        manifest = self.bundle/'region_samples.json'
        saved = manifest.read_bytes()
        try:
            source = copy.deepcopy(self.source)
            source['schema_version'] = True
            write_json(manifest, source)
            with self.assertRaises(ValueError): self.execute()
        finally:
            manifest.write_bytes(saved)

    def test_invalid_tolerance(self):
        with self.assertRaises(ValueError):
            run(self.video, self.bundle, self.ocr_path, self.gold_path,
                self.out, tolerance_seconds=True)

    def test_missing_ffprobe(self):
        with self.assertRaises(ValueError):
            run(self.video, self.bundle, self.ocr_path, self.gold_path,
                self.out, ffprobe='nonexistent_ffprobe_plo')

    def test_ambiguous_ocr_abstains(self):
        obj = copy.deepcopy(self.ocr)
        obj['candidates'][0]['raw_ocr_text'] = 'R$ 12'
        write_json(self.ocr_path, obj)
        report = self.execute()
        self.assertGreaterEqual(report['unparseable_or_ambiguous_abstentions'], 1)
        self.assertFalse(report['ready_for_equity_or_ev'])


if __name__ == '__main__':
    unittest.main()
