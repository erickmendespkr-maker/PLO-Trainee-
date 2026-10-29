"""Fail-closed unit tests for the offline source-replayed clip bundle."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import offline_source_replayed_triage_clip as mod


class SourceReplayedClipTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.inputs = [self.root / name for name in (
            'video.mp4', 'regions.json', 'ingest', 'changes.json', 'refined',
            'tasks.json', 'ocr', 'drafts.json', 'review.json', 'crop.json',
            'timeline.json', 'triage.json')]
        for i, p in enumerate(self.inputs):
            if i in (2, 4, 6):
                p.mkdir()
            else:
                p.write_bytes(b'example-' + str(i).encode())
        (self.inputs[6] / 'roi_ocr_proposals.json').write_bytes(b'ocr')
        self.out = self.root / 'output'
        self.calls = []
        self.audit_result = {
            'source_video_to_frame_to_roi_reproduced': True,
            'source_video_sha256': mod.sha(self.inputs[0]),
            'source_roi_ocr_report_sha256': mod.sha(self.inputs[6] / 'roi_ocr_proposals.json'),
            'source_frames_replayed_exactly': 2,
            'roi_pngs_replayed_exactly': 2,
            'ocr_semantics_verified': False,
            'ready_for_equity_or_ev': False,
        }
        self.export_modification = None
        self.audit_modification = None
        self.audit_calls = 0

    def audit(self, *args):
        self.audit_calls += 1
        if self.audit_modification:
            self.audit_modification(self.audit_calls)
        self.calls.append('audit')
        return dict(self.audit_result)

    def export(self, video, drafts, review, crop, timeline, triage,
               hand_id, proposal_index, clip_dir):
        self.calls.append('export')
        clip_dir = Path(clip_dir)
        clip_dir.mkdir()
        (clip_dir / 'clip.mp4').write_bytes(b'synthetic-mp4-placeholder')
        source_sha = mod.sha(video)
        clip_sha = mod.sha(clip_dir / 'clip.mp4')
        link = {
            'clip_sha256': clip_sha,
            'source_video_sha256': source_sha,
            'source_triage_sha256': mod.sha(triage),
            'source_timeline_sha256': mod.sha(timeline),
            'source_hand_drafts_sha256': mod.sha(drafts),
            'source_video_matches_ocr_source_verified': False,
            'ready_for_equity_or_ev': False,
            'hand_id': hand_id,
            'proposal_index': proposal_index,
        }
        manifest = {'clip_sha256': clip_sha,
                    'source_video_sha256': source_sha,
                    'ready_for_equity_or_ev': False}
        if self.export_modification:
            self.export_modification(link, manifest, clip_dir)
        (clip_dir / 'triage_clip_link.json').write_text(json.dumps(link))
        (clip_dir / 'manifest.json').write_text(json.dumps(manifest))
        return link

    def invoke(self, output=None):
        with mock.patch.object(mod, 'replay_audit', side_effect=self.audit), \
             mock.patch.object(mod, 'export_triage_clip', side_effect=self.export):
            return mod.run(*self.inputs, 'H4', 42, output or self.out)

    def assert_rejected(self):
        with self.assertRaises((ValueError, OSError)):
            self.invoke()
        self.assertFalse(self.out.exists())

    def test_success_binds_source_and_clip_and_two_audits(self):
        report = self.invoke()
        self.assertEqual(self.calls, ['audit', 'export', 'audit'])
        self.assertTrue(report['source_video_matches_clip_source_verified'])
        self.assertFalse(report['ocr_text_linked_to_replayed_roi_verified'])
        self.assertFalse(report['ready_for_equity_or_ev'])
        self.assertEqual(mod.sha(self.out / report['clip_path']), report['clip_sha256'])
        self.assertEqual(json.loads((self.out / 'source_replay_clip_attestation.json').read_text()), report)

    def test_reject_existing_output(self):
        self.out.mkdir()
        with self.assertRaises(ValueError):
            self.invoke()
        self.assertTrue(self.out.is_dir())

    def assert_rejected_for(self, output):
        with self.assertRaises(ValueError):
            self.invoke(output)
        self.assertFalse(output.exists())

    def test_reject_output_nested_inside_ingest(self):
        self.assert_rejected_for(self.inputs[2] / 'nested')

    def test_reject_output_nested_inside_ocr(self):
        self.assert_rejected_for(self.inputs[6] / 'nested')

    def test_reject_unsafe_output_name(self):
        self.assert_rejected_for(self.root / 'bad name')

    def test_reject_symlink_video(self):
        target = self.root / 'real-video'
        self.inputs[0].rename(target)
        self.inputs[0].symlink_to(target)
        self.assert_rejected()

    def test_reject_symlink_ocr_report(self):
        report = self.inputs[6] / 'roi_ocr_proposals.json'
        real = self.root / 'real-ocr'
        report.rename(real)
        report.symlink_to(real)
        self.assert_rejected()

    def test_reject_missing_file(self):
        self.inputs[5].unlink()
        self.assert_rejected()

    def test_reject_wrong_directory_type(self):
        self.inputs[2].rmdir()
        self.inputs[2].write_text('not a directory')
        self.assert_rejected()

    def test_reject_replay_video_mismatch(self):
        self.audit_result['source_video_sha256'] = '0' * 64
        self.assert_rejected()
        self.assertEqual(self.calls, ['audit'])

    def test_reject_no_replayed_frames(self):
        self.audit_result['source_frames_replayed_exactly'] = 0
        self.assert_rejected()

    def test_reject_no_replayed_rois(self):
        self.audit_result['roi_pngs_replayed_exactly'] = 0
        self.assert_rejected()

    def test_reject_ocr_semantics_claim(self):
        self.audit_result['ocr_semantics_verified'] = True
        self.assert_rejected()

    def test_reject_equity_claim(self):
        self.audit_result['ready_for_equity_or_ev'] = True
        self.assert_rejected()

    def test_reject_export_video_mismatch(self):
        self.export_modification = lambda link, manifest, folder: link.update(source_video_sha256='0'*64)
        self.assert_rejected()

    def test_reject_export_clip_hash_mismatch(self):
        self.export_modification = lambda link, manifest, folder: link.update(clip_sha256='0'*64)
        self.assert_rejected()

    def test_reject_export_timeline_hash_mismatch(self):
        self.export_modification = lambda link, manifest, folder: link.update(source_timeline_sha256='0'*64)
        self.assert_rejected()

    def test_reject_export_triage_hash_mismatch(self):
        self.export_modification = lambda link, manifest, folder: link.update(source_triage_sha256='0'*64)
        self.assert_rejected()

    def test_reject_export_drafts_hash_mismatch(self):
        self.export_modification = lambda link, manifest, folder: link.update(source_hand_drafts_sha256='0'*64)
        self.assert_rejected()

    def test_reject_export_mathematical_claim(self):
        self.export_modification = lambda link, manifest, folder: manifest.update(ready_for_equity_or_ev=True)
        self.assert_rejected()

    def test_reject_second_replay_mismatch(self):
        self.audit_modification = lambda count: self.audit_result.update(roi_pngs_replayed_exactly=1) if count == 2 else None
        self.assert_rejected()
        self.assertEqual(self.calls, ['audit', 'export', 'audit'])

    def test_reject_source_changed_during_export(self):
        self.export_modification = lambda link, manifest, folder: self.inputs[5].write_text('mutated')
        self.assert_rejected()

    def test_reject_output_race(self):
        self.export_modification = lambda link, manifest, folder: self.out.mkdir()
        with self.assertRaises(ValueError):
            self.invoke()
        self.assertTrue(self.out.is_dir())
        self.assertFalse((self.out / 'source_replay_clip_attestation.json').exists())

    def test_reject_clip_mutation_after_export(self):
        self.export_modification = lambda link, manifest, folder: (folder / 'clip.mp4').write_bytes(b'mutated')
        self.assert_rejected()


if __name__ == '__main__':
    unittest.main()
