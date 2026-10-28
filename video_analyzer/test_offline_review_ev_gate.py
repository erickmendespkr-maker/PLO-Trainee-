"""Synthetic offline gate integration tests; no GitHub Actions or real sessions."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from offline_human_observation_review import build as build_review
from offline_review_ev_gate import build, validate, render_html

FIXTURE = Path(__file__).resolve().parent.parent / 'demo'


class GateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.clips = self.root / 'exported_batch'
        self.clips.mkdir()
        self.video = self.root / 'synthetic_recording.mp4'
        self.packet = self.root / 'session_review.json'
        self.manual = self.root / 'manual_annotations.json'
        self.reviewed = self.root / 'reviewed.json'
        self.out = self.root / 'gate.json'
        self.html = self.root / 'gate.html'
        shutil.copyfile(FIXTURE / 'synthetic_recording.mp4', self.video)
        shutil.copyfile(FIXTURE / 'session_review.json', self.packet)
        for clip in (FIXTURE / 'exported_batch').glob('*.mp4'):
            shutil.copyfile(clip, self.clips / clip.name)
        self.manual.write_text(json.dumps({
            'schema_version': 1,
            'source_session_review_sha256': hashlib.sha256(self.packet.read_bytes()).hexdigest(),
            'reviewer_alias': 'test_local',
            'entries': [
                {'table_id': 1, 'hand_id': 'hand1', 'decision_id': 'd1', 'outcome': 'confirmed',
                 'corrected_observed_action': None, 'corrected_action_pts_seconds': None, 'note': ''},
                {'table_id': 2, 'hand_id': 'hand2', 'decision_id': 'd2', 'outcome': 'corrected',
                 'corrected_observed_action': 'raise', 'corrected_action_pts_seconds': 1.25,
                 'note': 'Ação corrigida ao revisar a gravação.'},
                {'table_id': 3, 'hand_id': 'hand3', 'decision_id': 'd3', 'outcome': 'inconclusive',
                 'corrected_observed_action': None, 'corrected_action_pts_seconds': None,
                 'note': 'Imagem ambígua, não há certeza sobre a ação.'},
            ]
        }, ensure_ascii=False), encoding='utf-8')
        build_review(self.video, self.clips, self.packet, self.manual,
                     self.reviewed, self.root / 'reviewed.html')

    def gate(self):
        return build(self.video, self.clips, self.packet, self.manual,
                     self.reviewed, self.out, self.html)

    def edit_json(self, path, fn):
        data = json.loads(path.read_text(encoding='utf-8'))
        fn(data)
        path.write_text(json.dumps(data), encoding='utf-8')

    def test_four_statuses(self):
        report = self.gate()
        statuses = [r['ev_interpretation_status'] for r in report['decisions']]
        self.assertEqual(statuses, [
            'conditional_model_only',
            'blocked_stale_observation_requires_recalculation',
            'blocked_inconclusive_observation',
            'blocked_pending_review'])
        self.assertEqual([r['may_display_hypothetical_ev'] for r in report['decisions']],
                         [True, False, False, False])
        self.assertEqual(report['decisions'][0]['observed_ev_interval_units'], ['20', '30'])
        self.assertTrue(all(r['observed_ev_interval_units'] is None for r in report['decisions'][1:]))
        self.assertFalse(report['equity_ev_recomputed'])
        self.assertEqual(sum(report['status_counts'].values()), 4)
        self.assertTrue(self.out.exists() and self.html.exists())

    def test_json_output_matches_return(self):
        self.assertEqual(self.gate(), json.loads(self.out.read_text(encoding='utf-8')))

    def test_source_files_not_changed(self):
        paths = [self.video, self.packet, self.manual, self.reviewed, *self.clips.glob('*.mp4')]
        hashes = [hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]
        self.gate()
        self.assertEqual(hashes, [hashlib.sha256(p.read_bytes()).hexdigest() for p in paths])

    def test_no_overwrite(self):
        self.out.write_text('keep')
        with self.assertRaises(ValueError): self.gate()
        self.assertEqual(self.out.read_text(), 'keep')
        self.assertFalse(self.html.exists())

    def test_reject_same_output(self):
        with self.assertRaises(ValueError):
            build(self.video, self.clips, self.packet, self.manual, self.reviewed, self.out, self.out)

    def test_reject_outside_directory(self):
        with self.assertRaises(ValueError):
            build(self.video, self.clips, self.packet, self.manual, self.reviewed,
                  self.root / 'outside' / 'gate.json', self.html)

    def test_reject_source_overwrite(self):
        with self.assertRaises(ValueError):
            build(self.video, self.clips, self.packet, self.manual, self.reviewed, self.packet, self.html)

    def test_reject_modified_clip(self):
        with (self.clips / 'table2.mp4').open('ab') as stream: stream.write(b'tampered')
        with self.assertRaises(ValueError): self.gate()
        self.assertFalse(self.out.exists())

    def test_reject_modified_recording(self):
        with self.video.open('ab') as stream: stream.write(b'tampered')
        with self.assertRaises(ValueError): self.gate()

    def test_reject_modified_packet(self):
        self.edit_json(self.packet, lambda d: d.update(warning='tampered'))
        with self.assertRaises(ValueError): self.gate()

    def test_reject_modified_annotations(self):
        self.edit_json(self.manual, lambda d: d['entries'][0].update(note='tampered'))
        with self.assertRaises(ValueError): self.gate()

    def test_reject_tampered_review_action(self):
        self.edit_json(self.reviewed, lambda d: d['decisions'][0].update(original_observed_action='raise'))
        with self.assertRaises(ValueError): self.gate()

    def test_reject_tampered_review_note(self):
        self.edit_json(self.reviewed, lambda d: d['decisions'][1]['review'].update(note='tampered'))
        with self.assertRaises(ValueError): self.gate()

    def test_reject_promoted_ev_flag(self):
        self.edit_json(self.reviewed, lambda d: d.update(equity_ev_recomputed=True))
        with self.assertRaises(ValueError): self.gate()

    def test_reject_promoted_recommendation(self):
        self.edit_json(self.reviewed, lambda d: d.update(action_recommendation_authorized=True))
        with self.assertRaises(ValueError): self.gate()

    def test_reject_reordered_decisions(self):
        self.edit_json(self.reviewed, lambda d: d['decisions'].reverse())
        with self.assertRaises(ValueError): self.gate()

    def test_reject_missing_decision(self):
        self.edit_json(self.reviewed, lambda d: d['decisions'].pop())
        with self.assertRaises(ValueError): self.gate()

    def test_reject_review_count_mismatch(self):
        self.edit_json(self.reviewed, lambda d: d.update(reviewed_decision_count=2))
        with self.assertRaises(ValueError): self.gate()

    def test_reject_duplicate_json_keys(self):
        with self.reviewed.open('a') as stream: stream.write(' {"duplicate":1}')
        with self.assertRaises(ValueError): self.gate()

    def test_reject_symlink_clip(self):
        clip = self.clips / 'table1.mp4'
        clip.rename(self.root / 'saved.mp4')
        clip.symlink_to(self.root / 'saved.mp4')
        with self.assertRaises(ValueError): self.gate()

    def test_html_does_not_include_source_note(self):
        report = self.gate()
        html = self.html.read_text(encoding='utf-8')
        self.assertIn('blocked_stale_observation_requires_recalculation', html)
        self.assertNotIn('Ação corrigida ao revisar', html)
        self.assertNotIn('https://', html)
        self.assertNotIn('<script', html)

    def test_html_escape(self):
        report = {'decisions':[{'table_id':1, 'hand_id':'<script>alert(1)</script>',
                                'decision_id':'<img src=x>',
                                'ev_interpretation_status':'blocked_pending_review'}]}
        html = render_html(report)
        self.assertIn('&lt;script&gt;', html)
        self.assertNotIn('<script>alert', html)

    def test_source_evidence_remains_unverified(self):
        report = self.gate()
        self.assertFalse(report['ranges_verified'])
        self.assertFalse(report['reviewer_identity_authenticated'])
        self.assertFalse(report['decision_quality_verified'])
        self.assertFalse(report['automatic_clip_selection_authorized'])

    def test_reject_nan_in_report(self):
        self.reviewed.write_text(self.reviewed.read_text().replace('"schema_version": 1',
                               '"schema_version": NaN', 1))
        with self.assertRaises(ValueError): self.gate()


if __name__ == '__main__': unittest.main()
