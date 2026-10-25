"""Synthetic-only tests for human visual verdicts; no poker accuracy claim."""
import copy
import json
import shutil
import tempfile
from pathlib import Path
import unittest

from hand_action_review_gallery import export as export_gallery
from hand_action_visual_verdicts import (build_template, validate, verified_gallery,
                                         export)
import test_hand_action_review_gallery as gallery_tests


class VisualVerdictTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        gallery_tests.GalleryTests.setUpClass()
        cls.video = gallery_tests.GalleryTests.video
        cls.fixture = gallery_tests.GalleryTests(methodName='test_four_tables_gallery_and_html')
        cls.fixture.video = cls.video
        gallery_tests.GalleryTests.setUp(cls.fixture)
        export_gallery(cls.video, cls.fixture.nav_path, cls.fixture.review_path,
                       cls.fixture.stills, cls.fixture.gallery,
                       regions_json=cls.fixture.regions)

    @classmethod
    def tearDownClass(cls):
        cls.fixture.doCleanups()
        gallery_tests.GalleryTests.tearDownClass()

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        shutil.copytree(self.fixture.root, self.root, dirs_exist_ok=True)
        self.nav_path = self.root / 'navigation.json'
        self.review_path = self.root / 'review.json'
        self.regions = self.root / 'regions.json'
        self.stills = self.root / 'stills'
        self.gallery = self.root / 'gallery'
        self.kw = {'regions_json': self.regions}
        self.gallery_data, self.digest = verified_gallery(
            self.video, self.nav_path, self.review_path, self.stills,
            self.gallery, self.regions)
        self.template = build_template(self.gallery_data, self.digest)

    def test_four_tables_template_and_no_math(self):
        rows = self.template['rows']
        self.assertEqual(len(rows), 24)
        self.assertEqual({r['table_id'] for r in rows}, {1, 2, 3, 4})
        self.assertEqual(sum(r['verdict'] == 'pending' for r in rows), 8)
        self.assertEqual(sum(r['verdict'] == 'unreviewable' for r in rows), 16)
        self.assertFalse(self.template['ready_for_equity_or_ev'])
        self.assertFalse(self.template['automatic_clip_selection_authorized'])

    def test_confirmed_and_rejected_still_do_not_authorize_math(self):
        edited = copy.deepcopy(self.template)
        rows = [r for r in edited['rows'] if r['verdict'] == 'pending']
        for row, verdict in zip(rows, ('confirmed_visual', 'rejected_visual')):
            row.update(verdict=verdict, reviewer='synthetic human',
                       notes='Reviewed synthetic pixels', visual_confidence=0.75)
        result = validate(self.gallery_data, self.digest, edited)
        self.assertEqual(result['counts']['confirmed_visual'], 1)
        self.assertEqual(result['counts']['rejected_visual'], 1)
        self.assertFalse(result['cards_or_actions_verified'])
        self.assertFalse(result['ready_for_equity_or_ev'])
        self.assertEqual(result['analysis_status'], 'manual_visual_verdicts_unverified_hand_no_math')

    def test_unknown_hypothesis_cannot_be_confirmed(self):
        edited = copy.deepcopy(self.template)
        row = next(r for r in edited['rows'] if r['verdict'] == 'unreviewable')
        row.update(verdict='confirmed_visual', reviewer='synthetic human',
                   notes='Invented confirmation', visual_confidence=1.0)
        with self.assertRaisesRegex(ValueError, 'Cannot review'):
            validate(self.gallery_data, self.digest, edited)

    def test_reviewer_and_rationale_required(self):
        edited = copy.deepcopy(self.template)
        row = next(r for r in edited['rows'] if r['verdict'] == 'pending')
        row['verdict'] = 'uncertain'
        with self.assertRaisesRegex(ValueError, 'reviewer'):
            validate(self.gallery_data, self.digest, edited)
        row.update(reviewer='human', notes='Uncertain still', visual_confidence=0.4)
        self.assertEqual(validate(self.gallery_data, self.digest, edited)['counts']['uncertain'], 1)

    def test_nan_boolean_and_out_of_range_confidence_rejected(self):
        for confidence in (float('nan'), float('inf'), True, -0.1, 1.1, None):
            with self.subTest(confidence=confidence):
                edited = copy.deepcopy(self.template)
                row = next(r for r in edited['rows'] if r['verdict'] == 'pending')
                row.update(verdict='confirmed_visual', reviewer='human',
                           notes='Enough rationale', visual_confidence=confidence)
                with self.assertRaises(ValueError):
                    validate(self.gallery_data, self.digest, edited)

    def test_source_digest_and_identity_are_immutable(self):
        for key in ('source_gallery_sha256', 'recording_sha256'):
            edited = copy.deepcopy(self.template)
            edited[key] = '0' * 64
            with self.assertRaises(ValueError):
                validate(self.gallery_data, self.digest, edited)
        edited = copy.deepcopy(self.template)
        edited['rows'][0]['table_id'] = 4
        with self.assertRaises(ValueError):
            validate(self.gallery_data, self.digest, edited)
        edited = copy.deepcopy(self.template)
        edited['rows'].reverse()
        with self.assertRaises(ValueError):
            validate(self.gallery_data, self.digest, edited)

    def test_forged_authority_and_pending_notes_rejected(self):
        edited = copy.deepcopy(self.template)
        edited['ready_for_equity_or_ev'] = True
        with self.assertRaises(ValueError):
            validate(self.gallery_data, self.digest, edited)
        edited = copy.deepcopy(self.template)
        edited['rows'][0]['notes'] = 'unreviewed note'
        with self.assertRaises(ValueError):
            validate(self.gallery_data, self.digest, edited)

    def test_tampered_png_and_stale_gallery_rejected(self):
        frame = next(r['frame_sha256'] for r in self.template['rows'] if r['frame_sha256'])
        filename = next(f['filename'] for f in json.loads(
            (self.stills / 'action_pts_evidence.json').read_text())['frames']
            if f['png_sha256'] == frame)
        (self.stills / filename).write_bytes(b'bad png')
        with self.assertRaises(ValueError):
            verified_gallery(self.video, self.nav_path, self.review_path,
                             self.stills, self.gallery, self.regions)

    def test_modified_gallery_json_rejected(self):
        path = self.gallery / 'review_gallery.json'
        obj = json.loads(path.read_text())
        obj['entries'][0]['links'][0]['status'] = 'invented'
        path.write_text(json.dumps(obj))
        with self.assertRaisesRegex(ValueError, 'stale'):
            verified_gallery(self.video, self.nav_path, self.review_path,
                             self.stills, self.gallery, self.regions)

    def test_template_finalize_and_no_overwrite(self):
        target = self.root / 'visual_template.json'
        form = export('template', self.video, self.nav_path, self.review_path,
                      self.stills, self.gallery, target, **self.kw)
        self.assertEqual(json.loads(target.read_text()), form)
        with self.assertRaises(ValueError):
            export('template', self.video, self.nav_path, self.review_path,
                   self.stills, self.gallery, target, **self.kw)
        edited = json.loads(target.read_text())
        row = next(r for r in edited['rows'] if r['verdict'] == 'pending')
        row.update(verdict='confirmed_visual', reviewer='synthetic reviewer',
                   notes='Synthetic still inspected', visual_confidence=0.6)
        edited_path = self.root / 'edited.json'
        edited_path.write_text(json.dumps(edited))
        output = self.root / 'verdicts.json'
        report = export('finalize', self.video, self.nav_path, self.review_path,
                        self.stills, self.gallery, edited_path, output, **self.kw)
        self.assertEqual(report['counts']['confirmed_visual'], 1)
        self.assertEqual(json.loads(output.read_text()), report)
        with self.assertRaises(ValueError):
            export('finalize', self.video, self.nav_path, self.review_path,
                   self.stills, self.gallery, edited_path, output, **self.kw)

    def test_duplicate_annotation_rejected(self):
        gallery = copy.deepcopy(self.gallery_data)
        gallery['entries'][0]['links'].append(copy.deepcopy(gallery['entries'][0]['links'][0]))
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            build_template(gallery, self.digest)

    def test_invalid_review_verdict_and_extra_fields_rejected(self):
        edited = copy.deepcopy(self.template)
        edited['rows'][0]['verdict'] = 'auto_verified'
        with self.assertRaises(ValueError):
            validate(self.gallery_data, self.digest, edited)
        edited = copy.deepcopy(self.template)
        edited['rows'][0]['equity'] = 1.0
        with self.assertRaises(ValueError):
            validate(self.gallery_data, self.digest, edited)

    def test_source_review_change_rejected(self):
        review = json.loads(self.review_path.read_text())
        review['entries'][0]['reviewer_notes'] = 'modified after gallery'
        self.review_path.write_text(json.dumps(review))
        with self.assertRaises(ValueError):
            verified_gallery(self.video, self.nav_path, self.review_path,
                             self.stills, self.gallery, self.regions)

    def test_no_regions_rejected_for_four_tables(self):
        with self.assertRaises(ValueError):
            verified_gallery(self.video, self.nav_path, self.review_path,
                             self.stills, self.gallery)


if __name__ == '__main__':
    unittest.main()
