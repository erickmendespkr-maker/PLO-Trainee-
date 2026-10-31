"""Synthetic tests for strict visual review import; no visual truth inferred."""
import copy
import json
import unittest

import offline_visual_evidence_review_import as importer
import offline_visual_evidence_review_ui as visual
from test_offline_hand_frame_evidence_audit import EvidenceAuditTests


class VisualImportTests(unittest.TestCase):
    def setUp(self):
        self.fx = EvidenceAuditTests('test_matching_frame_bytes_not_visual_truth')
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        f = self.fx
        self.draft_path = f.root / 'visual_draft.json'
        self.output = f.root / 'visual_import.json'
        self.draft = self.make_draft()
        self.write()

    def make_draft(self):
        packet = visual.build(self.fx.ocr_file, self.fx.rec_file, self.fx.review_file, self.fx.frames)
        return {'schema_version': 1, 'status': 'offline_visual_review_untrusted_draft',
                'source_review_sha256': packet['source_review_sha256'],
                'source_frame_manifest_sha256': packet['source_frame_manifest_sha256'],
                'source_video_sha256_claim': packet['source_video_sha256_claim'],
                'reviewer_claims_not_authenticated': True, 'math_ready': False,
                'eligible_for_equity': 0, 'equity_or_ev_calculated': False,
                'claims': [{'hand_id': c['hand_id'], 'table_id': c['table_id'],
                            'field': c['field'], 'slot': c['slot'],
                            'value_unverified': c['value_unverified'],
                            'visual_review_status': 'uncertain', 'reviewer_note': '',
                            'evidence': [{'frame_sha256': e['sha256'], 'pts_seconds': e['pts'],
                                          'observation_index': e['observation_index']}
                                         for e in c['evidence']]} for c in packet['cards']]}

    def write(self):
        self.draft_path.write_text(json.dumps(self.draft), encoding='utf-8')

    def run_import(self):
        f = self.fx
        return importer.build(f.ocr_file, f.rec_file, f.review_file, f.frames, self.draft_path)

    def test_default_uncertain(self):
        result = self.run_import()
        self.assertEqual(result['uncertain'], 1)
        self.assertEqual(result['eligible_for_equity'], 0)
        self.assertFalse(result['equity_or_ev_calculated'])
        self.assertTrue(result['video_content_not_semantically_verified'])

    def test_seen_is_only_unverified_assertion(self):
        self.draft['claims'][0]['visual_review_status'] = 'seen_by_reviewer'
        self.draft['claims'][0]['reviewer_note'] = 'Carta legível neste quadro'
        self.write()
        result = self.run_import()
        self.assertEqual(result['seen_by_reviewer_unverified'], 1)
        self.assertFalse(result['claims'][0]['video_content_semantically_verified'])
        self.assertFalse(result['claims'][0]['math_ready'])

    def test_not_visible(self):
        self.draft['claims'][0]['visual_review_status'] = 'not_visible'
        self.write()
        self.assertEqual(self.run_import()['not_visible_by_reviewer_unverified'], 1)

    def test_tampered_evidence_hash(self):
        self.draft['claims'][0]['evidence'][0]['frame_sha256'] = 'f'*64
        self.write()
        with self.assertRaisesRegex(ValueError, 'evidence altered'): self.run_import()

    def test_tampered_timestamp(self):
        self.draft['claims'][0]['evidence'][0]['pts_seconds'] = 10.2
        self.write()
        with self.assertRaisesRegex(ValueError, 'evidence altered'): self.run_import()

    def test_tampered_observation_index(self):
        self.draft['claims'][0]['evidence'][0]['observation_index'] = 999
        self.write()
        with self.assertRaisesRegex(ValueError, 'evidence altered'): self.run_import()

    def test_tampered_claim_value(self):
        self.draft['claims'][0]['value_unverified'] = 'Kd'
        self.write()
        with self.assertRaisesRegex(ValueError, 'evidence altered'): self.run_import()

    def test_tampered_claim_hand(self):
        self.draft['claims'][0]['hand_id'] = 'H2'
        self.write()
        with self.assertRaisesRegex(ValueError, 'evidence altered'): self.run_import()

    def test_provenance_tampering(self):
        self.draft['source_review_sha256'] = '0'*64
        self.write()
        with self.assertRaisesRegex(ValueError, 'provenance'): self.run_import()

    def test_math_flag_forgery(self):
        self.draft['eligible_for_equity'] = True
        self.write()
        with self.assertRaisesRegex(ValueError, 'safety flags'): self.run_import()

    def test_extra_root_key(self):
        self.draft['math_queue'] = []
        self.write()
        with self.assertRaisesRegex(ValueError, 'root'): self.run_import()

    def test_extra_claim_key(self):
        self.draft['claims'][0]['authenticated'] = True
        self.write()
        with self.assertRaisesRegex(ValueError, 'fields'): self.run_import()

    def test_duplicate_claim(self):
        self.draft['claims'].append(copy.deepcopy(self.draft['claims'][0]))
        self.write()
        with self.assertRaisesRegex(ValueError, 'count'): self.run_import()

    def test_missing_claim(self):
        self.draft['claims'] = []
        self.write()
        with self.assertRaisesRegex(ValueError, 'count'): self.run_import()

    def test_invalid_status(self):
        self.draft['claims'][0]['visual_review_status'] = 'verified'
        self.write()
        with self.assertRaisesRegex(ValueError, 'status'): self.run_import()

    def test_oversized_note(self):
        self.draft['claims'][0]['reviewer_note'] = 'x'*501
        self.write()
        with self.assertRaisesRegex(ValueError, 'note'): self.run_import()

    def test_control_char_note(self):
        self.draft['claims'][0]['reviewer_note'] = 'a\x00b'
        self.write()
        with self.assertRaisesRegex(ValueError, 'note'): self.run_import()

    def test_frame_tamper(self):
        self.fx.frame_file.write_bytes(b'tampered')
        with self.assertRaises(ValueError): self.run_import()

    def test_unmatched_claim_cannot_be_seen(self):
        import offline_hand_street_review_import as reviewed_import
        self.fx.draft['hands'][0]['fields'][0]['reviewer_value'] = 'Kd'
        self.fx.draft_file.write_text(json.dumps(self.fx.draft))
        self.fx.review_file.write_text(json.dumps(reviewed_import.build(
            self.fx.rec_file, self.fx.worksheet_file, self.fx.draft_file)))
        self.draft = self.make_draft()
        self.draft['claims'][0]['visual_review_status'] = 'seen_by_reviewer'
        self.write()
        with self.assertRaisesRegex(ValueError, 'cannot mark'): self.run_import()

    def test_unmatched_claim_can_be_uncertain(self):
        import offline_hand_street_review_import as reviewed_import
        self.fx.draft['hands'][0]['fields'][0]['reviewer_value'] = 'Kd'
        self.fx.draft_file.write_text(json.dumps(self.fx.draft))
        self.fx.review_file.write_text(json.dumps(reviewed_import.build(
            self.fx.rec_file, self.fx.worksheet_file, self.fx.draft_file)))
        self.draft = self.make_draft()
        self.write()
        self.assertEqual(self.run_import()['uncertain'], 1)

    def test_duplicate_json_key(self):
        self.draft_path.write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaisesRegex(ValueError, 'duplicate JSON key'): self.run_import()

    def test_nan_rejected(self):
        self.draft_path.write_text('{"schema_version":NaN}')
        with self.assertRaisesRegex(ValueError, 'nonfinite JSON'): self.run_import()

    def test_cli_no_overwrite(self):
        f = self.fx
        args = [str(f.ocr_file), str(f.rec_file), str(f.review_file), str(f.frames),
                str(self.draft_path), str(self.output)]
        self.assertEqual(importer.main(args), 0)
        self.assertEqual(json.loads(self.output.read_text())['eligible_for_equity'], 0)
        with self.assertRaisesRegex(ValueError, 'new distinct'): importer.main(args)


if __name__ == '__main__': unittest.main()
