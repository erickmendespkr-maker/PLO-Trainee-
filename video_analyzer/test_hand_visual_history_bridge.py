"""Synthetic tests for still-verdict -> unverified hand-history evidence linkage."""
import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from hand_action_visual_verdicts import build_template, validate, verified_gallery
from hand_visual_history_bridge import build, export
import test_hand_action_visual_verdicts as verdict_tests


class HistoryBridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        verdict_tests.VisualVerdictTests.setUpClass()
        cls.fixture = verdict_tests.VisualVerdictTests.fixture
        cls.video = verdict_tests.VisualVerdictTests.video

    @classmethod
    def tearDownClass(cls):
        verdict_tests.VisualVerdictTests.tearDownClass()

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        shutil.copytree(self.fixture.root, self.root, dirs_exist_ok=True)
        self.nav = self.root / 'navigation.json'
        self.review_path = self.root / 'review.json'
        self.stills = self.root / 'stills'
        self.gallery_dir = self.root / 'gallery'
        self.regions = self.root / 'regions.json'
        self.gallery, self.gallery_sha = verified_gallery(
            self.video, self.nav, self.review_path, self.stills,
            self.gallery_dir, self.regions)
        self.review = json.loads(self.review_path.read_text())
        self.edited = build_template(self.gallery, self.gallery_sha)
        self.verdicts = validate(self.gallery, self.gallery_sha, self.edited)
        self.digest = 'f' * 64

    def linked(self, verdicts=None, review=None):
        return build(review or self.review, self.gallery, self.gallery_sha,
                     verdicts or self.verdicts, self.digest)

    def test_four_tables_and_no_math(self):
        linked = self.linked()
        self.assertEqual(linked['counts']['spans'], 4)
        self.assertEqual(linked['counts']['annotations'], 24)
        self.assertEqual({r['table_id'] for r in linked['entries']}, {1, 2, 3, 4})
        self.assertEqual(linked['counts']['pending'], 8)
        self.assertEqual(linked['counts']['unreviewable'], 16)
        self.assertFalse(linked['ready_for_equity_or_ev'])
        self.assertFalse(linked['cards_or_actions_verified'])
        self.assertFalse(linked['automatic_clip_selection_authorized'])
        self.assertTrue(all(not r['hand_reconstruction_verified'] for r in linked['entries']))

    def test_confirmed_still_never_upgrades_hand_or_math(self):
        row = next(r for r in self.edited['rows'] if r['verdict'] == 'pending')
        row.update(verdict='confirmed_visual', reviewer='synthetic reviewer',
                   notes='Pixels appear to match this annotation', visual_confidence=0.8)
        result = self.linked(validate(self.gallery, self.gallery_sha, self.edited))
        item = result['entries'][0]['annotations'][0]
        self.assertEqual(item['visual_verdict'], 'confirmed_visual')
        self.assertEqual(item['evidence_status'], 'human_still_review_only_not_hand_verified')
        self.assertEqual(item['claimed_value'], 'PLO5')
        self.assertFalse(item['ready_for_equity_or_ev'])
        self.assertFalse(result['strategic_error_established'])

    def test_rejection_and_uncertainty_retained(self):
        pending = [r for r in self.edited['rows'] if r['verdict'] == 'pending']
        for row, verdict in zip(pending, ('rejected_visual', 'uncertain')):
            row.update(verdict=verdict, reviewer='synthetic reviewer',
                       notes='The synthetic image is not conclusive', visual_confidence=0.4)
        result = self.linked(validate(self.gallery, self.gallery_sha, self.edited))
        self.assertEqual(result['counts']['rejected_visual'], 1)
        self.assertEqual(result['counts']['uncertain'], 1)
        self.assertTrue(all(a['evidence_status'] == 'not_visually_confirmed'
                            for e in result['entries'] for a in e['annotations']))

    def test_hypotheses_remain_unreviewable(self):
        linked = self.linked()
        hyp = linked['entries'][0]['annotations'][2]
        self.assertEqual(hyp['source_kind'], 'hypothesis')
        self.assertEqual(hyp['visual_verdict'], 'unreviewable')
        self.assertIsNone(hyp['still_sha256'])

    def test_forged_final_counts_rejected(self):
        bad = copy.deepcopy(self.verdicts)
        bad['counts']['confirmed_visual'] = 1
        with self.assertRaisesRegex(ValueError, 'authentic finalized'):
            self.linked(bad)

    def test_forged_final_authority_rejected(self):
        bad = copy.deepcopy(self.verdicts)
        bad['ready_for_equity_or_ev'] = True
        with self.assertRaises(ValueError):
            self.linked(bad)

    def test_forged_final_row_identity_rejected(self):
        bad = copy.deepcopy(self.verdicts)
        bad['rows'][0]['table_id'] = 3
        with self.assertRaises(ValueError):
            self.linked(bad)

    def test_forged_frame_hash_rejected(self):
        bad = copy.deepcopy(self.verdicts)
        bad['rows'][0]['frame_sha256'] = '0' * 64
        with self.assertRaises(ValueError):
            self.linked(bad)

    def test_missing_entry_rejected(self):
        bad = copy.deepcopy(self.review)
        bad['entries'].pop()
        with self.assertRaises(ValueError):
            self.linked(review=bad)

    def test_export_revalidates_and_no_overwrite(self):
        verdict_path = self.root / 'visual_verdicts.json'
        verdict_path.write_text(json.dumps(self.verdicts))
        output = self.root / 'linked.json'
        kw = {'regions_json': self.regions}
        result = export(self.video, self.nav, self.review_path, self.stills,
                        self.gallery_dir, verdict_path, output, **kw)
        self.assertEqual(json.loads(output.read_text()), result)
        self.assertEqual(result['source_visual_verdicts_sha256'],
                         __import__('hashlib').sha256(verdict_path.read_bytes()).hexdigest())
        with self.assertRaisesRegex(ValueError, 'Output must be new'):
            export(self.video, self.nav, self.review_path, self.stills,
                   self.gallery_dir, verdict_path, output, **kw)

    def test_output_inside_evidence_directory_rejected(self):
        verdict_path = self.root / 'visual_verdicts.json'
        verdict_path.write_text(json.dumps(self.verdicts))
        with self.assertRaisesRegex(ValueError, 'outside evidence'):
            export(self.video, self.nav, self.review_path, self.stills,
                   self.gallery_dir, verdict_path, self.stills / 'linked.json',
                   regions_json=self.regions)

    def test_tampered_png_rejected(self):
        verdict_path = self.root / 'visual_verdicts.json'
        verdict_path.write_text(json.dumps(self.verdicts))
        png = next(self.stills.glob('*.png'))
        png.write_bytes(b'bad png')
        with self.assertRaises(ValueError):
            export(self.video, self.nav, self.review_path, self.stills,
                   self.gallery_dir, verdict_path, self.root / 'linked.json',
                   regions_json=self.regions)

    def test_unfinalized_template_rejected(self):
        with self.assertRaises(ValueError):
            self.linked(self.edited)


if __name__ == '__main__':
    unittest.main()
