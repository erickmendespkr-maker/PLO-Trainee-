"""Synthetic template generation and explicit-approval boundary tests."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from activity_review_clip_export import build_review_clip_plan
from activity_review_clip_template import build_clip_selection_template, main
from test_activity_review_clip_export import NeutralReviewClipsTests


class ClipTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        NeutralReviewClipsTests.setUpClass()
        cls.fixture = NeutralReviewClipsTests

    @classmethod
    def tearDownClass(cls):
        NeutralReviewClipsTests.tearDownClass()

    def test_template_is_unapproved_and_sha_bound(self):
        f = self.fixture
        result = build_clip_selection_template(f.video, f.queue, f.draft)
        self.assertEqual(len(result['selections']), 4)
        self.assertFalse(result['regions_human_confirmed'])
        self.assertEqual({r['table_id'] for r in result['regions']}, {1, 2, 3, 4})
        self.assertTrue(all(e['reviewer_approved'] is False for e in result['selections']))
        with self.assertRaisesRegex(ValueError, 'crop regions'):
            build_review_clip_plan(f.video, f.queue, f.draft, result)

    def test_manual_confirmation_required_for_each_selection(self):
        f = self.fixture
        result = build_clip_selection_template(f.video, f.queue, f.draft)
        result['regions_human_confirmed'] = True
        with self.assertRaises(ValueError):
            build_review_clip_plan(f.video, f.queue, f.draft, result)
        for e in result['selections']:
            e['reviewer_approved'] = True
            e['reviewer_priority'] = .5
            e['explanation'] = 'Revisado manualmente (sintético)'
        self.assertEqual(len(build_review_clip_plan(f.video, f.queue, f.draft, result)['clips']), 4)

    def test_tampered_queue_rejected_before_video_check(self):
        f = self.fixture
        queue = copy.deepcopy(f.queue); queue['recording_sha256'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'Protected field'):
            build_clip_selection_template(f.video, queue, f.draft)

    def test_cli_does_not_overwrite(self):
        f = self.fixture
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, data in [('queue', f.queue), ('draft', f.draft)]:
                (root / f'{name}.json').write_text(json.dumps(data))
            args = [str(f.video), str(root/'queue.json'), str(root/'draft.json'),
                    str(root/'selection.json')]
            self.assertEqual(main(args), 0)
            self.assertEqual(len(json.loads((root/'selection.json').read_text())['selections']), 4)
            with self.assertRaises(ValueError): main(args)
            with self.assertRaises(ValueError): main(args[:-1]+[args[1]])


if __name__ == '__main__':
    unittest.main()
