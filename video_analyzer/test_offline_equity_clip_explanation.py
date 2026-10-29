"""Offline HTML report tests, synthetic evidence only."""
import json
from pathlib import Path
import tempfile
import unittest

import offline_equity_clip_explanation as h
import offline_reviewed_equity_clip_report as m


class OfflineExplanationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.clip = self.root/'clip.mp4'
        self.clip.write_bytes(b'synthetic test clip placeholder')
        self.html = self.root/'explanation.html'
        self.report = {
            'schema_version':1,
            'analysis_status':'offline_conditional_manual_cards_equity_not_action_grade',
            'source_clip_sha256':m.digest(self.clip),
            'binding_replay_audit_rerun':False,
            'manual_cards_claimed_reviewed_not_independently_verified':True,
            'hero_actor_at_selected_action_verified':False,
            'selected_action_strategic_correctness_verified':False,
            'ocr_semantics_verified':False,
            'opponent_range_is_assumption':True,
            'variant':'PLO6','hand_id':'H4',
            'selected_action_ocr_text_not_graded':'raise <script>alert(1)</script>',
            'equity_result':{
                'analysis_status':'offline_manual_assumptions_monte_carlo_only',
                'strategic_correctness_verified':False,
                'ocr_semantics_verified':False,
                'player_identity_verified':False,
                'equity':0.6,'equity_ci95_sampling_only':[0.55,0.65],
                'iterations':2000,'seed':42,'variant':'PLO6',
                'opponent_model_kind':'weighted_combos',
            },
        }
        self.path = self.root/'report.json'
        self.save()

    def save(self):
        self.path.write_text(json.dumps(self.report))

    def test_html_escapes_untrusted_ocr(self):
        s = h.render(self.report,m.digest(self.clip))
        self.assertIn('&lt;script&gt;',s)
        self.assertNotIn('<script>',s)
        self.assertIn('60.00%',s)
        self.assertIn('55.00%',s)
        self.assertIn('src="clip.mp4"',s)
        self.assertNotIn('https://',s)

    def test_no_ev_without_pot(self):
        self.assertIn('não calculado',h.render(self.report,m.digest(self.clip)))

    def test_terminal_ev_label_hypothetical(self):
        self.report['equity_result']['terminal_call_ev_model']={
            'raise_ev':None,'call_ev_incremental':5.5}
        self.assertIn('hipotético',h.render(self.report,m.digest(self.clip)))

    def test_create_file(self):
        self.assertEqual(h.main([str(self.path),str(self.clip),str(self.html)]),0)
        self.assertTrue(self.html.exists())
        with self.assertRaises(ValueError):
            h.main([str(self.path),str(self.clip),str(self.html)])

    def test_manual_frame_evidence_displayed_as_claim(self):
        self.report['card_frame_evidence_count'] = 11
        self.report['card_frame_evidence_claimed_not_independently_verified'] = True
        html = h.render(self.report, m.digest(self.clip))
        self.assertIn('11 cartas', html)
        self.assertIn('declarações humanas', html)

    def test_reject_inconsistent_frame_evidence_metadata(self):
        self.report['card_frame_evidence_count'] = 11
        self.report['card_frame_evidence_claimed_not_independently_verified'] = False
        with self.assertRaises(ValueError): h.render(self.report, m.digest(self.clip))

    def test_legacy_no_frame_evidence(self):
        self.assertIn('não informados', h.render(self.report, m.digest(self.clip)))

    def test_reject_bad_clip_hash(self):
        with self.assertRaises(ValueError): h.render(self.report,'0'*64)

    def test_reject_claimed_actor(self):
        self.report['hero_actor_at_selected_action_verified']=True
        with self.assertRaises(ValueError): h.render(self.report,m.digest(self.clip))

    def test_reject_bad_ci(self):
        self.report['equity_result']['equity_ci95_sampling_only']=[0.8,0.9]
        with self.assertRaises(ValueError): h.render(self.report,m.digest(self.clip))

    def test_reject_bad_status(self):
        self.report['analysis_status']='strategic_grade'
        with self.assertRaises(ValueError): h.render(self.report,m.digest(self.clip))

    def test_reject_nonmatching_variant(self):
        self.report['variant']='PLO5'
        with self.assertRaises(ValueError): h.render(self.report,m.digest(self.clip))

    def test_reject_wrong_output_directory(self):
        other = self.root/'other'; other.mkdir()
        with self.assertRaises(ValueError):
            h.main([str(self.path),str(self.clip),str(other/'explanation.html')])

    def test_reject_different_clip_basename(self):
        other = self.root/'other.mp4'; other.write_bytes(b'placeholder')
        with self.assertRaises(ValueError):
            h.main([str(self.path),str(other),str(self.html)])


if __name__ == '__main__':
    unittest.main()
