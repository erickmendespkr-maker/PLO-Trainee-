"""Synthetic contract and integration tests for offline boundary review import."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from offline_boundary_annotation_import import build, transform
from offline_reviewed_hand_drafts import build as build_drafts


def dump(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.reviewed = self.root / 'reviewed.json'
        self.report = {'schema_version': 1,
                       'analysis_status': 'offline_human_reviewed_ocr_observations_only',
                       'source_roi_ocr_report_sha256': 'a'*64,
                       'ready_for_equity_or_ev': False, 'hands_reconstructed': False,
                       'observations': [
                           {'proposal_index': 0, 'table_id': 1, 'decoded_source_pts_seconds': 2,
                            'field': 'pot', 'decision': 'confirmed', 'normalized_value': '125.00',
                            'source_frame_sha256': 'b'*64, 'roi_png_sha256': 'c'*64},
                           {'proposal_index': 1, 'table_id': 2, 'decoded_source_pts_seconds': 2,
                            'field': 'action', 'decision': 'pending', 'normalized_value': None,
                            'source_frame_sha256': 'd'*64, 'roi_png_sha256': 'e'*64}]}
        dump(self.reviewed, self.report)
        self.orig_boundaries = self.root / 'original_boundaries.json'
        dump(self.orig_boundaries, {'schema_version': 1, 'reviewed_report_sha256': sha(self.reviewed),
                                    'hands': [
                                        {'hand_id': 'H1', 'table_id': 1, 'variant': 'PLO5',
                                         'start_seconds': 0, 'end_seconds': 10, 'note': 'Synthetic 1'},
                                        {'hand_id': 'H2', 'table_id': 2, 'variant': 'PLO6',
                                         'start_seconds': 0, 'end_seconds': 10, 'note': 'Synthetic 2'}]})
        self.draft_dir = self.root / 'drafts'
        build_drafts(self.reviewed, self.orig_boundaries, self.draft_dir)
        self.drafts = self.draft_dir / 'hand_drafts.json'
        self.annotations_path = self.root / 'annotations.json'
        self.annotations = {
            'schema_version': 1, 'source_hand_drafts_sha256': sha(self.drafts),
            'review_kind': 'manual_boundaries_only', 'ready_for_equity_or_ev': False,
            'annotations': [
                {'hand_id': 'H1', 'table_id': 1, 'review_status': 'pending',
                 'start_seconds': 0, 'end_seconds': 10, 'note': ''},
                {'hand_id': 'H2', 'table_id': 2, 'review_status': 'inconclusive',
                 'start_seconds': 0, 'end_seconds': 10, 'note': 'Cannot see hand start'}]}
        self.save()

    def save(self):
        dump(self.annotations_path, self.annotations)

    def run_import(self, name='imported'):
        self.save()
        return build(self.drafts, self.annotations_path, self.reviewed, self.root / name)

    def test_import_preserves_unreviewed_status_and_ev_gate(self):
        boundaries, audit = self.run_import()
        self.assertEqual(len(boundaries['hands']), 2)
        self.assertEqual([x['review_status'] for x in audit['annotations']], ['pending', 'inconclusive'])
        self.assertFalse(audit['ready_for_equity_or_ev'])
        self.assertFalse(audit['reviewed_boundaries_are_poker_verified'])
        self.assertEqual(boundaries['reviewed_report_sha256'], sha(self.reviewed))

    def test_round_trip_with_real_draft_builder(self):
        self.annotations['annotations'][0].update(review_status='corrected',
            start_seconds=1, note='Corrected after inspecting the recording')
        self.run_import()
        rebuilt = build_drafts(self.reviewed, self.root/'imported'/'revised_boundaries.json',
                               self.root/'rebuilt')
        self.assertEqual(rebuilt['hands'][0]['start_seconds'], 1)
        self.assertFalse(rebuilt['ready_for_equity_or_ev'])
        self.assertFalse(rebuilt['hands_reconstructed'])
        self.assertEqual(rebuilt['hands'][0]['boundary_origin'], 'manual_unverified')

    def test_confirmed_unchanged(self):
        self.annotations['annotations'][0]['review_status'] = 'confirmed'
        self.assertEqual(self.run_import()[1]['annotations'][0]['review_status'], 'confirmed')

    def test_corrected_must_change(self):
        self.annotations['annotations'][0].update(review_status='corrected', note='Explained')
        with self.assertRaisesRegex(ValueError, 'Boundary changes'): self.run_import()

    def test_corrected_requires_note(self):
        self.annotations['annotations'][0].update(review_status='corrected', start_seconds=1)
        with self.assertRaisesRegex(ValueError, 'Boundary changes'): self.run_import()

    def test_pending_cannot_silently_change(self):
        self.annotations['annotations'][0]['end_seconds'] = 9
        with self.assertRaisesRegex(ValueError, 'Boundary changes'): self.run_import()

    def test_confirmed_cannot_silently_change(self):
        self.annotations['annotations'][0].update(review_status='confirmed', end_seconds=9)
        with self.assertRaisesRegex(ValueError, 'Boundary changes'): self.run_import()

    def test_inconclusive_cannot_silently_change(self):
        self.annotations['annotations'][1]['start_seconds'] = 1
        with self.assertRaisesRegex(ValueError, 'Boundary changes'): self.run_import()

    def test_missing_hand(self):
        self.annotations['annotations'].pop()
        with self.assertRaisesRegex(ValueError, 'annotations provenance'): self.run_import()

    def test_duplicate_hand(self):
        self.annotations['annotations'][1] = copy.deepcopy(self.annotations['annotations'][0])
        with self.assertRaisesRegex(ValueError, 'duplicate hand'): self.run_import()

    def test_cross_table_identity(self):
        self.annotations['annotations'][0]['table_id'] = 2
        with self.assertRaisesRegex(ValueError, 'Invalid boundary'): self.run_import()

    def test_mismatched_source_sha(self):
        self.annotations['source_hand_drafts_sha256'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'annotations provenance'): self.run_import()

    def test_mismatched_reviewed_report(self):
        self.report['observations'][0]['normalized_value'] = '100.00'
        dump(self.reviewed, self.report)
        with self.assertRaisesRegex(ValueError, 'source draft provenance'): self.run_import()

    def test_tampered_ev_flag(self):
        self.annotations['ready_for_equity_or_ev'] = True
        with self.assertRaisesRegex(ValueError, 'annotations provenance'): self.run_import()

    def test_nonfinite_json(self):
        self.annotations_path.write_text('{"start_seconds":NaN}')
        with self.assertRaisesRegex(ValueError, 'Nonfinite'): build(
            self.drafts, self.annotations_path, self.reviewed, self.root/'imported')

    def test_duplicate_json_keys(self):
        self.annotations_path.write_text('{"schema_version":1,"schema_version":1}')
        with self.assertRaisesRegex(ValueError, 'Duplicate JSON'): build(
            self.drafts, self.annotations_path, self.reviewed, self.root/'imported')

    def test_boolean_timestamp_rejected(self):
        self.annotations['annotations'][0]['start_seconds'] = True
        with self.assertRaisesRegex(ValueError, 'Invalid boundary'): self.run_import()

    def test_negative_or_inverted_timestamp(self):
        self.annotations['annotations'][0]['start_seconds'] = 11
        with self.assertRaisesRegex(ValueError, 'Invalid boundary'): self.run_import()

    def test_overlap_same_table(self):
        self.annotations['annotations'][1]['table_id'] = 1
        with self.assertRaisesRegex(ValueError, 'Invalid boundary'): self.run_import()
        # Explicit overlapping same-table intervals with distinct IDs.
        d = json.loads(self.drafts.read_text())
        d['hands'][1]['table_id'] = 1
        dump(self.drafts, d)
        self.annotations['source_hand_drafts_sha256'] = sha(self.drafts)
        self.annotations['annotations'][1]['table_id'] = 1
        with self.assertRaisesRegex(ValueError, 'Overlapping'): self.run_import()

    def test_parallel_tables_allowed(self):
        self.assertEqual(len(self.run_import()[0]['hands']), 2)

    def test_no_overwrite(self):
        (self.root/'imported').mkdir()
        with self.assertRaisesRegex(ValueError, 'Output directory'): self.run_import()

    def test_symlink_rejected(self):
        link = self.root/'link.json'; link.symlink_to(self.drafts)
        self.save()
        with self.assertRaisesRegex(ValueError, 'Unsafe JSON'): build(
            link, self.annotations_path, self.reviewed, self.root/'imported')

    def test_control_character_note_rejected(self):
        self.annotations['annotations'][0]['note'] = '\x01'
        with self.assertRaisesRegex(ValueError, 'Invalid boundary'): self.run_import()

    def test_html_text_is_only_data(self):
        self.annotations['annotations'][0].update(review_status='corrected',
            start_seconds=1, note='</script><script>alert(1)</script>')
        _, audit = self.run_import()
        self.assertEqual(audit['annotations'][0]['review_note'], '</script><script>alert(1)</script>')
        self.assertFalse(audit['ready_for_equity_or_ev'])

    def test_deterministic(self):
        self.run_import('out1'); self.run_import('out2')
        for filename in ('revised_boundaries.json','boundary_review_audit.json'):
            self.assertEqual((self.root/'out1'/filename).read_bytes(),
                             (self.root/'out2'/filename).read_bytes())

    def test_cli(self):
        self.save()
        p = subprocess.run([sys.executable,
            str(Path(__file__).with_name('offline_boundary_annotation_import.py')),
            str(self.drafts), str(self.annotations_path), str(self.reviewed), str(self.root/'cli')],
            capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(p.stdout)['hands'], 2)
        self.assertFalse(json.loads(p.stdout)['ready_for_equity_or_ev'])


if __name__ == '__main__':
    unittest.main()
