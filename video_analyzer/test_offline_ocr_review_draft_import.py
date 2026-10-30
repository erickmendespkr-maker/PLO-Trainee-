"""Synthetic-only tests for fail-closed OCR review draft import."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from test_offline_ocr_frame_review_page import make_fixture
import offline_ocr_frame_review_page as page
import offline_ocr_review_draft_import as importer


class DraftImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.folder, self.worksheet, _, _ = make_fixture(self.root)
        self.packet = page.build(self.folder, self.worksheet)
        self.draft = self.root / 'draft.json'
        self.output = self.root / 'ledger.json'
        self.data = {'schema_version': 1,
                     'status': 'human_review_draft_not_confirmed_for_math',
                     'source_plan_sha256': self.packet['source_plan_sha256'],
                     'source_worksheet_sha256': self.packet['source_worksheet_sha256'],
                     'source_frame_manifest_sha256': self.packet['source_frame_manifest_sha256'],
                     'eligible_for_equity': 0, 'equity_or_ev_calculated': False,
                     'decisions': []}
        for hand in self.packet['hands']:
            for obs in hand['observations']:
                frame = self.packet['frames'][obs['frame_index']] if obs['frame_index'] is not None else None
                self.data['decisions'].append({'hand_id': hand['hand_id'],
                    'table_id': hand['table_id'], 'field': obs['field'],
                    'slot': obs['slot'], 'pts_seconds': obs['pts_seconds'],
                    'decision': 'unknown', 'corrected_value': None,
                    'frame_sha256': frame['sha256'] if frame else None})
        self.save()

    def tearDown(self):
        self.tmp.cleanup()

    def save(self):
        self.draft.write_text(json.dumps(self.data), encoding='utf-8')

    def test_valid_unknown_remains_blocked(self):
        result = importer.build(self.folder, self.worksheet, self.draft)
        self.assertEqual(result['eligible_for_equity'], 0)
        self.assertTrue(result['human_selection_not_authenticated'])
        self.assertEqual(len(result['hands']), 2)

    def test_accepted_still_not_math_ready(self):
        self.data['decisions'][0]['decision'] = 'accepted'; self.save()
        result = importer.build(self.folder, self.worksheet, self.draft)
        self.assertFalse(result['hands'][0]['math_ready'])
        self.assertEqual(result['hands'][0]['selected_card_slots_unverified'], 1)

    def test_rejected_allowed(self):
        self.data['decisions'][0]['decision'] = 'rejected'; self.save()
        self.assertEqual(importer.build(self.folder, self.worksheet, self.draft)['decisions'][0]['human_selection_unverified'], 'rejected')

    def test_cli_creates_new_file(self):
        self.assertEqual(importer.main([str(self.folder), str(self.worksheet), str(self.draft), str(self.output)]), 0)
        self.assertTrue(self.output.exists())
        with self.assertRaisesRegex(ValueError, 'new distinct'):
            importer.main([str(self.folder), str(self.worksheet), str(self.draft), str(self.output)])

    def test_wrong_plan_hash(self):
        self.data['source_plan_sha256'] = 'f'*64; self.save()
        with self.assertRaisesRegex(ValueError, 'provenance'):
            importer.build(self.folder, self.worksheet, self.draft)

    def test_wrong_worksheet_hash(self):
        self.data['source_worksheet_sha256'] = 'f'*64; self.save()
        with self.assertRaisesRegex(ValueError, 'provenance'):
            importer.build(self.folder, self.worksheet, self.draft)

    def test_wrong_frame_manifest_hash(self):
        self.data['source_frame_manifest_sha256'] = 'f'*64; self.save()
        with self.assertRaisesRegex(ValueError, 'provenance'):
            importer.build(self.folder, self.worksheet, self.draft)

    def test_wrong_frame_hash(self):
        self.data['decisions'][0]['frame_sha256'] = 'f'*64; self.save()
        with self.assertRaisesRegex(ValueError, 'frame hash'):
            importer.build(self.folder, self.worksheet, self.draft)

    def test_cross_table(self):
        self.data['decisions'][0]['table_id'] = 'T2'; self.save()
        with self.assertRaisesRegex(ValueError, 'observation mismatch'):
            importer.build(self.folder, self.worksheet, self.draft)

    def test_reordered_rows(self):
        self.data['decisions'].reverse(); self.save()
        with self.assertRaisesRegex(ValueError, 'observation mismatch'):
            importer.build(self.folder, self.worksheet, self.draft)

    def test_missing_row(self):
        self.data['decisions'].pop(); self.save()
        with self.assertRaisesRegex(ValueError, 'count mismatch'):
            importer.build(self.folder, self.worksheet, self.draft)

    def test_fake_equity(self):
        self.data['eligible_for_equity'] = 1; self.save()
        with self.assertRaisesRegex(ValueError, 'schema or provenance'):
            importer.build(self.folder, self.worksheet, self.draft)

    def test_bool_equity(self):
        self.data['eligible_for_equity'] = False; self.save()
        with self.assertRaisesRegex(ValueError, 'schema or provenance'):
            importer.build(self.folder, self.worksheet, self.draft)

    def test_corrected_accepted_rejected(self):
        self.data['decisions'][0]['decision'] = 'accepted'
        self.data['decisions'][0]['corrected_value'] = 'Kh'; self.save()
        with self.assertRaisesRegex(ValueError, 'corrected text'):
            importer.build(self.folder, self.worksheet, self.draft)

    def test_corrected_unknown_preserved(self):
        self.data['decisions'][0]['corrected_value'] = 'Kh'; self.save()
        result = importer.build(self.folder, self.worksheet, self.draft)
        self.assertEqual(result['decisions'][0]['corrected_text_unverified'], 'Kh')
        self.assertEqual(result['eligible_for_equity'], 0)

    def test_malicious_corrected_value_rejected(self):
        self.data['decisions'][0]['corrected_value'] = '\n'; self.save()
        with self.assertRaisesRegex(ValueError, 'observation mismatch'):
            importer.build(self.folder, self.worksheet, self.draft)

    def test_duplicate_json_keys_rejected(self):
        self.draft.write_text('{"a":1,"a":2}', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'duplicate JSON key'):
            importer.build(self.folder, self.worksheet, self.draft)

    def test_symlink_draft_rejected(self):
        other = self.root/'other.json'; self.draft.rename(other)
        self.draft.symlink_to(other)
        with self.assertRaisesRegex(ValueError, 'invalid review draft'):
            importer.build(self.folder, self.worksheet, self.draft)

    def test_altered_png_rejected(self):
        (self.folder/'frame_001.png').write_bytes(b'bad')
        with self.assertRaisesRegex(ValueError, 'altered frame'):
            importer.build(self.folder, self.worksheet, self.draft)

    def test_accept_without_matching_frame_rejected(self):
        worksheet = json.loads(self.worksheet.read_text())
        worksheet['hands'][0]['observations'][0]['pts_seconds'] = 11
        self.worksheet.write_text(json.dumps(worksheet))
        self.packet = page.build(self.folder, self.worksheet)
        self.data['source_worksheet_sha256'] = self.packet['source_worksheet_sha256']
        self.data['decisions'][0]['pts_seconds'] = 11
        self.data['decisions'][0]['decision'] = 'accepted'
        self.save()
        with self.assertRaisesRegex(ValueError, 'exact-time frame'):
            importer.build(self.folder, self.worksheet, self.draft)

    def test_nan_rejected(self):
        self.data['decisions'][0]['pts_seconds'] = float('nan'); self.save()
        with self.assertRaisesRegex(ValueError, 'nonfinite JSON'):
            importer.build(self.folder, self.worksheet, self.draft)

    def test_unknown_extra_field_rejected(self):
        self.data['decisions'][0]['manual_review_confirmed'] = True; self.save()
        with self.assertRaisesRegex(ValueError, 'decision fields'):
            importer.build(self.folder, self.worksheet, self.draft)


if __name__ == '__main__':
    unittest.main()
