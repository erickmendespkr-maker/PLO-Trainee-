"""Synthetic provenance tests; frame hashes never certify visible poker cards."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image
import offline_hand_frame_evidence_audit as audit
import offline_hand_street_review as review
import offline_hand_street_review_import as importer
import offline_ocr_hand_reconstruction as reconstruct


class EvidenceAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.frames = self.root / 'frames'
        self.frames.mkdir()
        self.ocr_file = self.root / 'ocr.json'
        self.rec_file = self.root / 'reconstruction.json'
        self.worksheet_file = self.root / 'worksheet.json'
        self.draft_file = self.root / 'draft.json'
        self.review_file = self.root / 'reviewed.json'
        self.out_file = self.root / 'audit.json'
        self.video_file = self.root / 'video.mp4'
        self.video_file.write_bytes(b'synthetic-video-only')
        self.ocr = json.loads(Path(__file__).with_name('ledger_fixture.json').read_text())
        self.ocr['hands'] = self.ocr['hands'][:1]
        self.ocr['decisions'] = self.ocr['decisions'][:1]
        self.ocr['source_video_sha256_claim'] = review.digest(self.video_file)
        self.ocr['source_plan_sha256'] = 'a' * 64
        self.ocr['source_worksheet_sha256'] = 'b' * 64
        self.ocr['source_draft_sha256'] = 'c' * 64
        self.frame_file = self.frames / 'frame_001.png'
        Image.new('RGB', (100, 100), 'white').save(self.frame_file)
        self.manifest = {'schema_version': 1,
                         'status': 'offline_multiframe_roi_geometry_unverified',
                         'ocr_confirmed': False, 'eligible_for_equity': 0,
                         'manual_review_required': True,
                         'source_video_sha256': self.ocr['source_video_sha256_claim'],
                         'source_plan_sha256': self.ocr['source_plan_sha256'],
                         'frames': [{'hand_id': 'H1', 'table_id': 'T1', 'pts_seconds': 10,
                                     'frame': self.frame_file.name,
                                     'frame_sha256': review.digest(self.frame_file)}]}
        self.refresh()

    def refresh(self):
        (self.frames/'manifest.json').write_text(json.dumps(self.manifest))
        self.ocr['source_frame_manifest_sha256'] = review.digest(self.frames/'manifest.json')
        self.ocr['decisions'][0]['frame_sha256'] = self.manifest['frames'][0]['frame_sha256']
        self.ocr_file.write_text(json.dumps(self.ocr))
        self.reconstruction = reconstruct.build(self.ocr, review.digest(self.ocr_file))
        self.rec_file.write_text(json.dumps(self.reconstruction))
        self.worksheet = review.worksheet(self.reconstruction, review.digest(self.rec_file))
        self.worksheet_file.write_text(json.dumps(self.worksheet))
        self.draft = copy.deepcopy(self.worksheet)
        self.draft['hands'][0]['fields'][0].update(review_status='confirmed_by_reviewer', reviewer_value='As')
        self.draft_file.write_text(json.dumps(self.draft))
        self.reviewed = importer.build(self.rec_file, self.worksheet_file, self.draft_file)
        self.review_file.write_text(json.dumps(self.reviewed))

    def run_audit(self, video=None):
        return audit.build(self.ocr_file, self.rec_file, self.review_file, self.frames, video)

    def test_matching_frame_bytes_not_visual_truth(self):
        result = self.run_audit()
        self.assertEqual(result['claims_with_frame_links'], 1)
        self.assertEqual(result['claims_without_frame_links'], 0)
        self.assertTrue(result['video_content_not_semantically_verified'])
        self.assertEqual(result['eligible_for_equity'], 0)
        self.assertFalse(result['hands'][0]['math_ready'])

    def test_frame_link_preserves_timestamp_and_sha(self):
        claim = self.run_audit()['hands'][0]['claims'][0]
        self.assertEqual(claim['matching_frame_observations'][0]['pts_seconds'], 10)
        self.assertEqual(claim['matching_frame_observations'][0]['frame_sha256'], review.digest(self.frame_file))
        self.assertTrue(claim['human_video_verification_required'])

    def test_video_hash_optional(self):
        self.assertFalse(self.run_audit()['source_video_hash_verified'])
        self.assertTrue(self.run_audit(self.video_file)['source_video_hash_verified'])

    def test_wrong_video_rejected(self):
        self.video_file.write_bytes(b'altered')
        with self.assertRaisesRegex(ValueError, 'video SHA-256 mismatch'):
            self.run_audit(self.video_file)

    def test_frame_tampering_rejected(self):
        self.frame_file.write_bytes(b'altered')
        with self.assertRaisesRegex(ValueError, 'altered frame bytes'):
            self.run_audit()

    def test_manifest_tampering_rejected(self):
        self.manifest['frames'][0]['pts_seconds'] = 20
        (self.frames/'manifest.json').write_text(json.dumps(self.manifest))
        with self.assertRaisesRegex(ValueError, 'manifest provenance mismatch'):
            self.run_audit()

    def test_manifest_video_mismatch(self):
        self.manifest['source_video_sha256'] = 'f' * 64
        self.refresh()
        with self.assertRaisesRegex(ValueError, 'manifest provenance mismatch'):
            self.run_audit()

    def test_manifest_plan_mismatch(self):
        self.manifest['source_plan_sha256'] = 'f' * 64
        self.refresh()
        with self.assertRaisesRegex(ValueError, 'manifest provenance mismatch'):
            self.run_audit()

    def test_timestamp_outside_tolerance_is_unmatched(self):
        self.manifest['frames'][0]['pts_seconds'] = 10.5
        self.refresh()
        result = self.run_audit()
        self.assertEqual(result['claims_with_frame_links'], 0)
        self.assertEqual(result['claims_without_frame_links'], 1)

    def test_unaccepted_ocr_is_not_linked(self):
        self.ocr['decisions'][0]['human_selection_unverified'] = 'unknown'
        self.ocr['hands'][0]['selected_card_slots_unverified'] = 0
        self.refresh()
        result = self.run_audit()
        self.assertEqual(result['claims_with_frame_links'], 0)

    def test_manual_correction_does_not_inherit_frame_proof(self):
        self.refresh()
        self.draft['hands'][0]['fields'][0]['reviewer_value'] = 'Kd'
        self.draft_file.write_text(json.dumps(self.draft))
        self.reviewed = importer.build(self.rec_file, self.worksheet_file, self.draft_file)
        self.review_file.write_text(json.dumps(self.reviewed))
        result = self.run_audit()
        self.assertEqual(result['claims_without_frame_links'], 1)
        self.assertEqual(result['eligible_for_equity'], 0)

    def test_review_ledger_tampering_rejected(self):
        self.reviewed['eligible_for_equity'] = 1
        self.review_file.write_text(json.dumps(self.reviewed))
        with self.assertRaisesRegex(ValueError, 'review ledger provenance mismatch'):
            self.run_audit()

    def test_reconstruction_tampering_rejected(self):
        self.reconstruction['hands'][0]['review_flags'].append('forged')
        self.rec_file.write_text(json.dumps(self.reconstruction))
        with self.assertRaisesRegex(ValueError, 'reconstruction differs'):
            self.run_audit()

    def test_wrong_reconstruction_hash_rejected(self):
        self.reviewed['source_reconstruction_sha256'] = 'f' * 64
        self.review_file.write_text(json.dumps(self.reviewed))
        with self.assertRaisesRegex(ValueError, 'review ledger provenance mismatch'):
            self.run_audit()

    def test_duplicate_review_field_rejected(self):
        self.reviewed['hands'][0]['fields'].append(copy.deepcopy(self.reviewed['hands'][0]['fields'][0]))
        self.review_file.write_text(json.dumps(self.reviewed))
        with self.assertRaisesRegex(ValueError, 'duplicate review field'):
            self.run_audit()

    def test_symlink_frame_rejected(self):
        other = self.root/'other.png'
        self.frame_file.rename(other)
        self.frame_file.symlink_to(other)
        with self.assertRaisesRegex(ValueError, 'altered frame bytes'):
            self.run_audit()

    def test_cli_creates_new_file_and_no_overwrite(self):
        args = [str(self.ocr_file), str(self.rec_file), str(self.review_file),
                str(self.frames), str(self.out_file)]
        self.assertEqual(audit.main(args), 0)
        self.assertEqual(json.loads(self.out_file.read_text())['eligible_for_equity'], 0)
        with self.assertRaisesRegex(ValueError, 'new distinct'):
            audit.main(args)

    def test_duplicate_json_key_rejected(self):
        self.review_file.write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaisesRegex(ValueError, 'duplicate JSON key'):
            self.run_audit()

    def test_nonfinite_json_rejected(self):
        self.review_file.write_text('{"schema_version":NaN}')
        with self.assertRaisesRegex(ValueError, 'nonfinite JSON'):
            self.run_audit()


if __name__ == '__main__':
    unittest.main()
