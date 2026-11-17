"""Regression tests for conservative recorded-video review journal."""
import unittest
from offline_review_journal import create_review_journal

RID = 'a' * 64
HASH = 'b' * 64

def fixture():
    return {'source': 'offline_recorded_video', 'video_sha256': HASH, 'tasks': [
        {'review_id': RID, 'review_status': 'PENDING',
         'strategic_commentary_allowed': False,
         'evidence': {'table_id': '1', 'earliest_pts': 2.0, 'latest_pts': 4.0}}]}

class ReviewJournalTests(unittest.TestCase):
    def test_pending(self):
        j = create_review_journal(fixture())
        self.assertEqual(j['entries'][0]['decision']['status'], 'PENDING')
        self.assertFalse(j['entries'][0]['strategic_commentary_allowed'])

    def test_deterministic(self):
        self.assertEqual(create_review_journal(fixture()), create_review_journal(fixture()))

    def test_reviewed_does_not_authorize_strategy(self):
        j = create_review_journal(fixture(), [
            {'review_id': RID, 'status': 'REVIEWED', 'reviewer_note': 'Visual review only'}])
        self.assertFalse(j['entries'][0]['strategic_commentary_allowed'])

    def test_unknown_review_rejected(self):
        with self.assertRaises(ValueError):
            create_review_journal(fixture(), [
                {'review_id': 'c' * 64, 'status': 'REJECTED', 'reviewer_note': ''}])

    def test_duplicate_decision_rejected(self):
        decision = {'review_id': RID, 'status': 'REJECTED', 'reviewer_note': ''}
        with self.assertRaises(ValueError):
            create_review_journal(fixture(), [decision, decision])

    def test_untrusted_task_rejected(self):
        h = fixture()
        h['tasks'][0]['strategic_commentary_allowed'] = True
        with self.assertRaises(ValueError):
            create_review_journal(h)

    def test_nonfinite_timestamp_rejected(self):
        h = fixture()
        h['tasks'][0]['evidence']['earliest_pts'] = float('nan')
        with self.assertRaises(ValueError):
            create_review_journal(h)

    def test_review_requires_note(self):
        with self.assertRaises(ValueError):
            create_review_journal(fixture(), [
                {'review_id': RID, 'status': 'REVIEWED', 'reviewer_note': ' '}])

if __name__ == '__main__':
    unittest.main()
