"""Synthetic-only offline OCR review UI tests; no real poker footage."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from PIL import Image

import offline_ocr_frame_review_page as review


def make_fixture(root, tables=2):
    folder = root / 'frames'; folder.mkdir()
    frames = []
    hands = []
    for i in range(tables):
        name = f'frame_{i+1:03d}.png'
        image = folder / name
        Image.new('RGB', (128, 72), (25+i, 35, 45)).save(image)
        frames.append({'hand_id': f'H{i+1}', 'table_id': f'T{i+1}',
                       'pts_seconds': 10+i, 'frame': name,
                       'frame_sha256': review.sha256(image),
                       'editor': f'frame_{i+1:03d}.html', 'editor_sha256': 'b'*64})
        hands.append({'hand_id': f'H{i+1}', 'table_id': f'T{i+1}',
                      'start_seconds': 9+i, 'end_seconds': 12+i,
                      'human_review_required': True, 'machine_cards_confirmed': False,
                      'eligible_for_equity': False,
                      'observations': [{'hand_id': f'H{i+1}', 'table_id': f'T{i+1}',
                                        'field': 'hero_card', 'slot': 0,
                                        'value': 'As', 'pts_seconds': 10+i,
                                        'confidence': 0.99, 'roi': {'x':.1,'y':.1,'w':.2,'h':.2},
                                        'engine': 'synthetic'}]})
    manifest = {'schema_version': 1, 'status': 'offline_multiframe_roi_geometry_unverified',
                'source_video_sha256': 'a'*64, 'source_plan_sha256': 'b'*64,
                'ocr_confirmed': False, 'eligible_for_equity': 0,
                'manual_review_required': True, 'frames': frames}
    worksheet = {'schema_version': 1, 'status': 'ocr_review_worksheet_not_confirmed',
                 'source_plan_sha256': 'b'*64, 'source_proposals_sha256': 'c'*64,
                 'source_video_sha256_claim': 'a'*64,
                 'card_claims_verified': False, 'equity_or_ev_calculated': False,
                 'hands': hands}
    manifest_path = folder / 'manifest.json'
    worksheet_path = root / 'worksheet.json'
    manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
    worksheet_path.write_text(json.dumps(worksheet), encoding='utf-8')
    return folder, worksheet_path, manifest, worksheet


class OfflineReviewPageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.folder, self.worksheet_path, self.manifest, self.worksheet = make_fixture(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def save(self):
        (self.folder/'manifest.json').write_text(json.dumps(self.manifest))
        self.worksheet_path.write_text(json.dumps(self.worksheet))

    def test_end_to_end_two_tables(self):
        packet = review.build(self.folder, self.worksheet_path)
        self.assertEqual(len(packet['frames']), 2)
        self.assertEqual(len(packet['hands']), 2)
        self.assertTrue(packet['hands'][0]['observations'][0]['can_accept_after_human_review'])
        self.assertEqual(packet['eligible_for_equity'], 0)
        self.assertFalse(packet['equity_or_ev_calculated'])
        page = review.render(packet)
        self.assertIn('connect-src \'none\'', page)
        self.assertIn('human_review_draft_not_confirmed_for_math', page)
        self.assertIn('data:image/png;base64,', page)
        self.assertNotIn('fetch(', page)

    def test_cli_new_file_and_no_overwrite(self):
        output = self.root / 'review.html'
        self.assertEqual(review.main([str(self.folder), str(self.worksheet_path), str(output)]), 0)
        self.assertTrue(output.is_file())
        with self.assertRaisesRegex(ValueError, 'distinct new'):
            review.main([str(self.folder), str(self.worksheet_path), str(output)])

    def test_four_tables(self):
        with tempfile.TemporaryDirectory() as d:
            folder, path, _, _ = make_fixture(Path(d), 4)
            self.assertEqual(len(review.build(folder, path)['hands']), 4)

    def test_ocr_confidence_one_never_auto_confirmed(self):
        self.worksheet['hands'][0]['observations'][0]['confidence'] = 1
        self.save()
        packet = review.build(self.folder, self.worksheet_path)
        self.assertEqual(packet['eligible_for_equity'], 0)
        self.assertTrue(packet['human_review_required'])

    def test_far_timestamp_blocks_accept(self):
        self.worksheet['hands'][0]['observations'][0]['pts_seconds'] = 11
        self.save()
        item = review.build(self.folder, self.worksheet_path)['hands'][0]['observations'][0]
        self.assertFalse(item['can_accept_after_human_review'])
        self.assertEqual(item['frame_delta_seconds'], 1)

    def test_wrong_table_does_not_bind_frame(self):
        self.worksheet['hands'][0]['table_id'] = 'T999'
        self.worksheet['hands'][0]['observations'][0]['table_id'] = 'T999'
        self.save()
        with self.assertRaisesRegex(ValueError, 'unbound frame'):
            review.build(self.folder, self.worksheet_path)

    def test_frame_timestamp_outside_hand_rejected(self):
        self.manifest['frames'][0]['pts_seconds'] = 8
        self.save()
        with self.assertRaisesRegex(ValueError, 'outside reviewed hand'):
            review.build(self.folder, self.worksheet_path)

    def test_tampered_png_rejected(self):
        (self.folder/'frame_001.png').write_bytes(b'not png')
        with self.assertRaisesRegex(ValueError, 'altered frame'):
            review.build(self.folder, self.worksheet_path)

    def test_corrupt_png_matching_hash_rejected(self):
        image = self.folder/'frame_001.png'
        image.write_bytes(b'bad image')
        self.manifest['frames'][0]['frame_sha256'] = review.sha256(image)
        self.save()
        with self.assertRaises(Exception):
            review.build(self.folder, self.worksheet_path)

    def test_path_traversal_rejected(self):
        self.manifest['frames'][0]['frame'] = '../worksheet.json'
        self.save()
        with self.assertRaisesRegex(ValueError, 'frame entry'):
            review.build(self.folder, self.worksheet_path)

    def test_duplicate_frame_rejected(self):
        self.manifest['frames'].append(copy.deepcopy(self.manifest['frames'][0]))
        self.save()
        with self.assertRaisesRegex(ValueError, 'frame entry'):
            review.build(self.folder, self.worksheet_path)

    def test_provenance_mismatch_rejected(self):
        self.worksheet['source_video_sha256_claim'] = 'f'*64
        self.save()
        with self.assertRaisesRegex(ValueError, 'provenance mismatch'):
            review.build(self.folder, self.worksheet_path)

    def test_fake_verified_worksheet_rejected(self):
        self.worksheet['card_claims_verified'] = True
        self.save()
        with self.assertRaisesRegex(ValueError, 'unverified OCR worksheet'):
            review.build(self.folder, self.worksheet_path)

    def test_fake_equity_manifest_rejected(self):
        self.manifest['eligible_for_equity'] = 1
        self.save()
        with self.assertRaisesRegex(ValueError, 'unverified frame manifest'):
            review.build(self.folder, self.worksheet_path)

    def test_cross_table_observation_rejected(self):
        self.worksheet['hands'][0]['observations'][0]['table_id'] = 'T2'
        self.save()
        with self.assertRaisesRegex(ValueError, 'observation'):
            review.build(self.folder, self.worksheet_path)

    def test_nan_confidence_rejected(self):
        self.worksheet['hands'][0]['observations'][0]['confidence'] = float('nan')
        self.save()
        with self.assertRaisesRegex(ValueError, 'nonfinite JSON'):
            review.build(self.folder, self.worksheet_path)

    def test_boolean_confidence_rejected(self):
        self.worksheet['hands'][0]['observations'][0]['confidence'] = True
        self.save()
        with self.assertRaisesRegex(ValueError, 'observation'):
            review.build(self.folder, self.worksheet_path)

    def test_html_injection_escaped(self):
        self.worksheet['hands'][0]['observations'][0]['value'] = '</script><img src=x>'
        self.save()
        page = review.render(review.build(self.folder, self.worksheet_path))
        self.assertNotIn('</script><img src=x>', page)
        self.assertIn('\\u003c/script>', page)

    def test_duplicate_json_key_rejected(self):
        self.worksheet_path.write_text('{"a":1,"a":2}')
        with self.assertRaisesRegex(ValueError, 'duplicate JSON key'):
            review.build(self.folder, self.worksheet_path)

    def test_symlink_frame_rejected(self):
        target = self.folder/'frame_001.png'
        other = self.root/'original.png'
        target.rename(other)
        target.symlink_to(other)
        with self.assertRaisesRegex(ValueError, 'altered frame'):
            review.build(self.folder, self.worksheet_path)

    def test_no_matching_frame_for_hand(self):
        self.manifest['frames'] = self.manifest['frames'][:1]
        (self.folder/'frame_002.png').unlink()
        self.save()
        packet = review.build(self.folder, self.worksheet_path)
        self.assertIsNone(packet['hands'][1]['observations'][0]['frame_index'])
        self.assertFalse(packet['hands'][1]['observations'][0]['can_accept_after_human_review'])


if __name__ == '__main__':
    unittest.main()
