"""Synthetic, offline card/frame form tests; no real session or OCR validation."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import offline_manual_card_review_form as m
import offline_reviewed_equity_clip_report as report


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


class ManualCardReviewFormTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.clip = self.root/'clip.mp4'
        self.clip.write_bytes(b'placeholder-not-real-mp4')
        self.binding = self.root/'binding.json'
        self.out = self.root/'manual_form.html'
        self.b = dict(schema_version=1,analysis_status='offline_selected_action_roi_clip_identity_only',
            hand_id='H4',table_id=4,variant='PLO6',proposal_index=2,timestamp_seconds=5.,
            reviewed_action_text='raise',roi_png_sha256='a'*64,source_video_sha256='b'*64,
            source_roi_ocr_report_sha256='c'*64,source_timeline_sha256='d'*64,
            source_triage_sha256='e'*64,source_clip_attestation_sha256='f'*64,
            clip_sha256=sha(self.clip),selected_action_to_replayed_roi_verified=True,
            selected_action_to_source_video_and_clip_verified=True,
            ocr_semantics_verified=False,actor_identified=False,hands_reconstructed=False,
            ready_for_equity_or_ev=False)
        self.write()

    def write(self):self.binding.write_text(json.dumps(self.b))

    def test_generate_offline_html(self):
        self.assertEqual(m.main([str(self.binding),str(self.clip),str(self.out)]),0)
        html=self.out.read_text()
        self.assertIn('Registrar quadro',html)
        self.assertIn(sha(self.clip),html)
        self.assertIn(sha(self.binding),html)
        self.assertIn('card_frame_evidence',html)
        self.assertNotIn('https://',html)
        self.assertNotIn('fetch(',html)

    def test_reject_reuse_output(self):
        m.main([str(self.binding),str(self.clip),str(self.out)])
        with self.assertRaises(ValueError):m.main([str(self.binding),str(self.clip),str(self.out)])

    def test_reject_clip_tamper(self):
        self.clip.write_bytes(b'altered')
        with self.assertRaisesRegex(ValueError,'clip hash'):m.build(self.binding,self.clip)

    def test_reject_binding_false_verified(self):
        self.b['selected_action_to_replayed_roi_verified']=False;self.write()
        with self.assertRaises(ValueError):m.build(self.binding,self.clip)

    def test_reject_actor_verified(self):
        self.b['actor_identified']=True;self.write()
        with self.assertRaises(ValueError):m.build(self.binding,self.clip)

    def test_reject_symlink_clip(self):
        link=self.root/'other.mp4';link.symlink_to(self.clip)
        with self.assertRaises(ValueError):m.build(self.binding,link)

    def test_reject_html_in_other_directory(self):
        dest=self.root/'sub';dest.mkdir()
        with self.assertRaises(ValueError):m.main([str(self.binding),str(self.clip),str(dest/'a.html')])

    def test_reject_non_clip_mp4_name(self):
        renamed=self.root/'video.mp4';renamed.write_bytes(self.clip.read_bytes())
        with self.assertRaises(ValueError):m.main([str(self.binding),str(renamed),str(self.out)])

    def test_reject_invalid_binding(self):
        self.b['table_id']=0;self.write()
        with self.assertRaises(ValueError):m.build(self.binding,self.clip)

    def test_escapes_script_injected_hand(self):
        self.b['reviewed_action_text']='</script><script>alert(1)</script>';self.write()
        html=m.build(self.binding,self.clip)
        self.assertNotIn('</script><script>alert',html)
        self.assertNotIn('alert(1)',html)


class CardFrameEvidenceValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.clip=self.root/'clip.mp4';self.clip.write_bytes(b'fake')
        self.binding=self.root/'binding.json';self.review=self.root/'review.json'
        self.b=dict(schema_version=1,analysis_status='offline_selected_action_roi_clip_identity_only',
            hand_id='H4',table_id=4,variant='PLO5',proposal_index=2,timestamp_seconds=5.,
            reviewed_action_text='raise',roi_png_sha256='a'*64,source_video_sha256='b'*64,
            source_roi_ocr_report_sha256='c'*64,source_timeline_sha256='d'*64,
            source_triage_sha256='e'*64,source_clip_attestation_sha256='f'*64,
            clip_sha256=sha(self.clip),selected_action_to_replayed_roi_verified=True,
            selected_action_to_source_video_and_clip_verified=True,
            ocr_semantics_verified=False,actor_identified=False,hands_reconstructed=False,
            ready_for_equity_or_ev=False)
        self.binding.write_text(json.dumps(self.b))
        hero=['As','Ks','2c','3d','4c'];board=['Qs','Js','Ts','8d','7c']
        self.r=dict(schema_version=1,source_binding_sha256=sha(self.binding),
            source_clip_sha256=sha(self.clip),hand_id='H4',table_id=4,proposal_index=2,
            variant='PLO5',manual_cards_confirmed=True,review_method='manual_video_frame_review',
            review_notes='Synthetic reviewer note.',hero_cards=hero,board_cards=board,
            opponent_model={'kind':'uniform'},iterations=2,seed=42,
            card_frame_evidence=[{'card':c,'clip_timestamp_seconds':1.25} for c in hero+board])
        self.write()

    def write(self):self.review.write_text(json.dumps(self.r))
    def build(self):return report.build(self.binding,self.clip,self.review)

    def test_valid_evidence_count(self):
        result=self.build()
        self.assertEqual(result['card_frame_evidence_count'],10)
        self.assertTrue(result['card_frame_evidence_claimed_not_independently_verified'])
        self.assertFalse(result['hero_actor_at_selected_action_verified'])

    def test_legacy_review_accepted(self):
        self.r.pop('card_frame_evidence');self.write()
        self.assertEqual(self.build()['card_frame_evidence_count'],0)

    def test_missing_card_rejected(self):
        self.r['card_frame_evidence'].pop();self.write()
        with self.assertRaises(ValueError):self.build()

    def test_extra_card_rejected(self):
        self.r['card_frame_evidence'][0]['card']='Ac';self.write()
        with self.assertRaises(ValueError):self.build()

    def test_duplicate_evidence_rejected(self):
        self.r['card_frame_evidence'][1]['card']='As';self.write()
        with self.assertRaises(ValueError):self.build()

    def test_nan_timestamp_rejected(self):
        self.r['card_frame_evidence'][0]['clip_timestamp_seconds']=float('nan');self.write()
        with self.assertRaises(ValueError):self.build()

    def test_boolean_timestamp_rejected(self):
        self.r['card_frame_evidence'][0]['clip_timestamp_seconds']=True;self.write()
        with self.assertRaises(ValueError):self.build()

    def test_negative_timestamp_rejected(self):
        self.r['card_frame_evidence'][0]['clip_timestamp_seconds']=-1;self.write()
        with self.assertRaises(ValueError):self.build()

    def test_unknown_evidence_field_rejected(self):
        self.r['card_frame_evidence'][0]['ocr_verified']=True;self.write()
        with self.assertRaises(ValueError):self.build()

    def test_evidence_not_list_rejected(self):
        self.r['card_frame_evidence']={};self.write()
        with self.assertRaises(ValueError):self.build()


if __name__=='__main__':unittest.main()
