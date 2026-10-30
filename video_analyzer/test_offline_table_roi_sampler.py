"""Synthetic-only tests. These do NOT measure recognition accuracy on real poker video."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image
import offline_table_roi_sampler as sampler
import offline_ffmpeg_tesseract_proposals as extractor
import offline_ocr_review_bridge as bridge
import offline_reviewed_hand_math_queue as queue
from test_offline_ffmpeg_tesseract_proposals import ExtractorTests


def template():
    tables = []
    for i in range(4):
        tables.append({
            'table_id': f'T{i+1}',
            'roi': {'x': (i % 2) / 2, 'y': (i // 2) / 2,
                    'w': .5, 'h': .5},
            'fields': [{'field': 'hero_card', 'slot': 0,
                        'roi': {'x': 185/640, 'y': 125/360,
                                'w': 200/640, 'h': 130/360}}]})
    return {'schema_version': 1,
            'status': 'human_declared_table_geometry_unverified',
            'fractions': [.5], 'tables': tables}


class RoiSamplerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ExtractorTests.setUpClass()
        cls.video, cls.plan, cls.plan_path = (ExtractorTests.video,
                                               ExtractorTests.plan,
                                               ExtractorTests.plan_path)

    @classmethod
    def tearDownClass(cls):
        ExtractorTests.tearDownClass()

    def build(self, tpl=None, plan=None):
        return sampler.build(plan or self.plan, tpl or template(), 1280, 720, 3)

    def test_four_table_spec_is_compatible_with_extractor(self):
        spec = self.build()
        self.assertEqual(len(spec['samples']), 4)
        clips = queue.validate_plan(self.plan)
        self.assertEqual(extractor.validate_spec(spec, clips, 3), spec['samples'])
        self.assertEqual([r['roi'] for r in spec['samples']],
                         [r['roi'] for r in __import__('test_offline_ffmpeg_tesseract_proposals').sample_spec()['samples']])

    def test_actual_ocr_synthetic_four_cards(self):
        observations, skipped, _ = extractor.build(self.video, self.plan, self.build())
        self.assertEqual([r['value'] for r in observations], ['As', 'Kd', 'Qh', 'Jc'])
        self.assertEqual(skipped, 0)

    def test_ocr_does_not_unlock_monte_carlo(self):
        observations, _, digest = extractor.build(self.video, self.plan, self.build())
        proposals = {'schema_version': 1, 'status': 'offline_ocr_proposals_unverified',
                     'source_plan_sha256': queue.digest(self.plan_path),
                     'source_video_sha256_claim': digest, 'observations': observations}
        _, annotations = bridge.build(self.plan, proposals, queue.digest(self.plan_path), '0'*64)
        result = queue.build(self.plan, annotations, queue.digest(self.plan_path), '0'*64)
        self.assertEqual(result['eligible_count'], 0)

    def test_multiple_fractions_are_deterministic(self):
        tpl = template(); tpl['fractions'] = [.25, .5, .75]
        a, b = self.build(tpl), self.build(tpl)
        self.assertEqual(a, b)
        self.assertEqual(len(a['samples']), 12)
        self.assertEqual(sorted({r['pts_seconds'] for r in a['samples']}), [1, 1.5, 2])

    def test_preview_and_cli_outputs(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            tpl = root / 'template.json'; tpl.write_text(json.dumps(template()))
            spec = root / 'samples.json'; png = root / 'preview.png'
            args = [str(self.video), str(self.plan_path), str(tpl), str(spec), str(png)]
            self.assertEqual(sampler.main(args), 0)
            self.assertEqual(len(queue.read(spec)['samples']), 4)
            with Image.open(png) as img:
                self.assertEqual(img.size, (1280, 720))
                self.assertEqual(img.format, 'PNG')
            with self.assertRaisesRegex(ValueError, 'distinct new'):
                sampler.main(args)

    def test_missing_table(self):
        tpl = template(); tpl['tables'].pop()
        with self.assertRaisesRegex(ValueError, 'cover all'):
            self.build(tpl)

    def test_duplicate_table(self):
        tpl = template(); tpl['tables'][1]['table_id'] = 'T1'
        with self.assertRaisesRegex(ValueError, 'template entry'):
            self.build(tpl)

    def test_overlapping_tables(self):
        tpl = template(); tpl['tables'][1]['roi']['x'] = .4
        with self.assertRaisesRegex(ValueError, 'overlapping'):
            self.build(tpl)

    def test_field_outside_table(self):
        tpl = template(); tpl['tables'][0]['fields'][0]['roi']['x'] = .99
        with self.assertRaisesRegex(ValueError, 'field rectangle'):
            self.build(tpl)

    def test_field_too_small(self):
        tpl = template(); tpl['tables'][0]['fields'][0]['roi']['w'] = .001
        with self.assertRaisesRegex(ValueError, 'too small'):
            self.build(tpl)

    def test_duplicate_field_slot(self):
        tpl = template(); tpl['tables'][0]['fields'].append(copy.deepcopy(tpl['tables'][0]['fields'][0]))
        with self.assertRaisesRegex(ValueError, 'duplicate field'):
            self.build(tpl)

    def test_bad_card_slot(self):
        tpl = template(); tpl['tables'][0]['fields'][0]['slot'] = True
        with self.assertRaisesRegex(ValueError, 'card slot'):
            self.build(tpl)

    def test_non_card_slot(self):
        tpl = template(); tpl['tables'][0]['fields'][0]['field'] = 'pot'
        with self.assertRaisesRegex(ValueError, 'null slot'):
            self.build(tpl)

    def test_fraction_bool_rejected(self):
        tpl = template(); tpl['fractions'] = [True]
        with self.assertRaisesRegex(ValueError, 'fractions'):
            self.build(tpl)

    def test_fraction_boundary_rejected(self):
        tpl = template(); tpl['fractions'] = [0]
        with self.assertRaisesRegex(ValueError, 'fractions'):
            self.build(tpl)

    def test_fraction_unsorted_rejected(self):
        tpl = template(); tpl['fractions'] = [.8, .2]
        with self.assertRaisesRegex(ValueError, 'fractions'):
            self.build(tpl)

    def test_duration_too_short(self):
        with self.assertRaisesRegex(ValueError, 'exceeds video'):
            sampler.build(self.plan, template(), 1280, 720, 2)

    def test_more_than_6000_samples_rejected(self):
        # 100 hands, 4 tables, 32 fields, 5 fractions => 16,000 samples.
        tpl = template(); tpl['fractions'] = [.1, .3, .5, .7, .9]
        for table in tpl['tables']:
            fields = []
            for i in range(6):
                fields.append({'field': 'hero_card', 'slot': i,
                               'roi': {'x': .1, 'y': .1, 'w': .2, 'h': .2}})
            for i in range(5):
                fields.append({'field': 'board_card', 'slot': i,
                               'roi': {'x': .1, 'y': .1, 'w': .2, 'h': .2}})
            table['fields'] = fields
        plan = copy.deepcopy(self.plan)
        plan['clips'] = []
        for i in range(100):
            plan['clips'].append({'hand_id': f'H{i}', 'table_id': f'T{i%4+1}',
                                 'start_seconds': .5, 'end_seconds': 2.5,
                                 'review_basis': 'human_declared_boundaries_not_automatic_detection'})
        # 100 * 11 * 5 = 5500, legal; add fields to reach >6000.
        for table in tpl['tables']:
            table['fields'].append({'field': 'pot', 'slot': None,
                                    'roi': {'x': .1, 'y': .1, 'w': .2, 'h': .2}})
            table['fields'].append({'field': 'stack', 'slot': None,
                                    'roi': {'x': .1, 'y': .1, 'w': .2, 'h': .2}})
        with self.assertRaisesRegex(ValueError, 'too many samples'):
            sampler.build(plan, tpl, 1280, 720, 3)

    def test_source_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); tpl = root / 'template.json'; tpl.write_text(json.dumps(template()))
            plan = copy.deepcopy(self.plan); plan['source_video_sha256'] = 'f'*64
            pp = root / 'plan.json'; pp.write_text(json.dumps(plan))
            with self.assertRaisesRegex(ValueError, 'SHA-256'):
                sampler.main([str(self.video), str(pp), str(tpl),
                              str(root/'out.json'), str(root/'out.png')])

    def test_output_alias_input_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); tpl = root / 'template.json'; tpl.write_text(json.dumps(template()))
            with self.assertRaisesRegex(ValueError, 'distinct new'):
                sampler.main([str(self.video), str(self.plan_path), str(tpl),
                              str(tpl), str(root/'out.png')])

    def test_preview_output_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); tpl = root / 'template.json'; tpl.write_text(json.dumps(template()))
            png = root/'preview.png'; png.symlink_to(self.video)
            with self.assertRaisesRegex(ValueError, 'distinct new'):
                sampler.main([str(self.video), str(self.plan_path), str(tpl),
                              str(root/'out.json'), str(png)])


if __name__ == '__main__':
    unittest.main()
