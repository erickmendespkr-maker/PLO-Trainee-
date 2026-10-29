"""Synthetic offline evidence-to-conditional-equity tests, not real-video validation."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import offline_reviewed_equity_clip_report as m


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


class ReviewedEquityClipReportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.clip = self.root / 'clip.mp4'
        self.clip.write_bytes(b'synthetic-mp4-placeholder-not-a-real-video')
        self.binding = self.root / 'binding.json'
        self.review = self.root / 'review.json'
        self.report = self.root / 'report.json'
        self.b = {
            'schema_version': 1,
            'analysis_status': 'offline_selected_action_roi_clip_identity_only',
            'hand_id': 'H4', 'table_id': 4, 'variant': 'PLO6',
            'proposal_index': 2, 'timestamp_seconds': 5.0,
            'reviewed_action_text': 'raise',
            'roi_png_sha256': 'a'*64,
            'source_video_sha256': 'b'*64,
            'source_roi_ocr_report_sha256': 'c'*64,
            'source_timeline_sha256': 'd'*64,
            'source_triage_sha256': 'e'*64,
            'source_clip_attestation_sha256': 'f'*64,
            'clip_sha256': sha(self.clip),
            'selected_action_to_replayed_roi_verified': True,
            'selected_action_to_source_video_and_clip_verified': True,
            'ocr_semantics_verified': False, 'actor_identified': False,
            'hands_reconstructed': False, 'ready_for_equity_or_ev': False,
        }
        self.write_binding()
        self.r = {
            'schema_version': 1,
            'source_binding_sha256': sha(self.binding),
            'source_clip_sha256': sha(self.clip),
            'hand_id': 'H4', 'table_id': 4, 'proposal_index': 2,
            'variant': 'PLO6',
            'manual_cards_confirmed': True,
            'review_method': 'manual_video_frame_review',
            'review_notes': 'Synthetic cards entered by reviewer for an offline test.',
            'hero_cards': ['As','Ks','2c','3d','4c','5d'],
            'board_cards': ['Qs','Js','Ts','8d','7c'],
            'opponent_model': {'kind':'weighted_combos','combos':[
                {'cards':['2h','3h','4h','5h','6h','7h'],'weight':1}]},
            'iterations': 20, 'seed': 42,
        }
        self.write_review()

    def write_binding(self):
        self.binding.write_text(json.dumps(self.b))

    def write_review(self):
        self.review.write_text(json.dumps(self.r))

    def build(self):
        return m.build(self.binding, self.clip, self.review)

    def test_known_royal_win_plo6(self):
        result = self.build()
        self.assertEqual(result['equity_result']['equity'], 1)
        self.assertEqual(result['equity_result']['win_count'], 20)
        self.assertFalse(result['selected_action_strategic_correctness_verified'])
        self.assertFalse(result['hero_actor_at_selected_action_verified'])
        self.assertFalse(result['binding_replay_audit_rerun'])
        self.assertEqual(result['source_manual_review_sha256'], sha(self.review))

    def test_reproducible_result(self):
        self.assertEqual(self.build(), self.build())

    def test_plo5_support(self):
        self.b['variant'] = 'PLO5'; self.write_binding()
        self.r['variant'] = 'PLO5'; self.r['hero_cards'] = self.r['hero_cards'][:5]
        self.r['opponent_model']['combos'][0]['cards'] = self.r['opponent_model']['combos'][0]['cards'][:5]
        self.r['source_binding_sha256'] = sha(self.binding); self.write_review()
        self.assertEqual(self.build()['equity_result']['variant'], 'PLO5')

    def test_hypothetical_call_ev_explicit(self):
        self.r.update(pot_now=100, call_cost=20); self.write_review()
        result = self.build()
        self.assertEqual(result['equity_result']['terminal_call_ev_model']['call_ev_incremental'],100)
        self.assertFalse(result['selected_action_strategic_correctness_verified'])

    def test_no_pot_no_ev(self):
        self.assertNotIn('terminal_call_ev_model', self.build()['equity_result'])

    def test_cli_creates_once(self):
        self.assertEqual(m.main([str(self.binding),str(self.clip),str(self.review),str(self.report)]),0)
        self.assertEqual(json.loads(self.report.read_text())['analysis_status'],
                         'offline_conditional_manual_cards_equity_not_action_grade')
        with self.assertRaises(ValueError):
            m.main([str(self.binding),str(self.clip),str(self.review),str(self.report)])

    def test_reject_binding_tamper(self):
        self.b['reviewed_action_text']='fold'; self.write_binding()
        with self.assertRaisesRegex(ValueError, 'fingerprints'):
            self.build()

    def test_reject_clip_tamper(self):
        self.clip.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'clip does not match'):
            self.build()

    def test_reject_review_clip_hash(self):
        self.r['source_clip_sha256'] = '0'*64; self.write_review()
        with self.assertRaises(ValueError): self.build()

    def test_reject_review_hand_mismatch(self):
        self.r['hand_id'] = 'H5'; self.write_review()
        with self.assertRaises(ValueError): self.build()

    def test_reject_review_table_mismatch(self):
        self.r['table_id'] = 3; self.write_review()
        with self.assertRaises(ValueError): self.build()

    def test_reject_review_variant_mismatch(self):
        self.r['variant'] = 'PLO5'; self.write_review()
        with self.assertRaises(ValueError): self.build()

    def test_reject_review_proposal_mismatch(self):
        self.r['proposal_index'] = 3; self.write_review()
        with self.assertRaises(ValueError): self.build()

    def test_reject_false_manual_confirmation(self):
        self.r['manual_cards_confirmed'] = False; self.write_review()
        with self.assertRaises(ValueError): self.build()

    def test_reject_ocr_as_review_method(self):
        self.r['review_method'] = 'OCR'; self.write_review()
        with self.assertRaises(ValueError): self.build()

    def test_reject_short_review_notes(self):
        self.r['review_notes'] = 'x'; self.write_review()
        with self.assertRaises(ValueError): self.build()

    def test_reject_hidden_card_claims(self):
        self.r['hidden_cards_inferred'] = True; self.write_review()
        with self.assertRaises(ValueError): self.build()

    def test_reject_manual_reviewed_ocr_direct(self):
        self.r['hero_cards'] = ['As','Ks','2c','3d','4c','As']; self.write_review()
        with self.assertRaises(ValueError): self.build()

    def test_reject_unreviewed_actor_claim(self):
        self.b['actor_identified'] = True; self.write_binding()
        self.r['source_binding_sha256'] = sha(self.binding); self.write_review()
        with self.assertRaises(ValueError): self.build()

    def test_reject_wrong_binding_status(self):
        self.b['analysis_status'] = 'offline_unverified'; self.write_binding()
        self.r['source_binding_sha256'] = sha(self.binding); self.write_review()
        with self.assertRaises(ValueError): self.build()

    def test_reject_invalid_range(self):
        self.r['opponent_model'] = {'kind':'unknown'}; self.write_review()
        with self.assertRaises(ValueError): self.build()

    def test_reject_no_pot_pair(self):
        self.r['pot_now'] = 100; self.write_review()
        with self.assertRaises(ValueError): self.build()

    def test_reject_symlink_clip(self):
        link = self.root/'link.mp4'
        link.symlink_to(self.clip)
        with self.assertRaises(ValueError): m.build(self.binding,link,self.review)

    def test_reject_duplicate_json_keys(self):
        self.review.write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaises(ValueError): self.build()

    def test_reject_nonfinite_timestamp(self):
        self.b['timestamp_seconds'] = float('nan'); self.write_binding()
        self.r['source_binding_sha256'] = sha(self.binding); self.write_review()
        with self.assertRaises(ValueError): self.build()

    def test_reject_boolean_table_id(self):
        self.b['table_id'] = True; self.write_binding()
        self.r['table_id'] = True
        self.r['source_binding_sha256'] = sha(self.binding); self.write_review()
        with self.assertRaises(ValueError): self.build()


if __name__ == '__main__':
    unittest.main()
