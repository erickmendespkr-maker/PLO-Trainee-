"""Identity and immutable EV-blocking checks for offline drafts."""
import copy
import unittest
from activity_review_draft_binding import check_draft_binding
from activity_review_packet import build_review_packet
from activity_snapshot_chain import build_activity_snapshot_queue
from test_activity_snapshot_chain import fixture


class DraftBindingTests(unittest.TestCase):
    def setUp(self):
        self.template = build_review_packet(build_activity_snapshot_queue(fixture()))['template']
        self.draft = copy.deepcopy(self.template)
        self.draft['analysis_status'] = 'manual_review_draft_unverified_no_ev'

    def test_four_table_binding_preserves_block(self):
        self.assertEqual(len(check_draft_binding(self.template, self.draft)), 4)
        self.assertFalse(self.draft['ready_for_equity_or_ev'])

    def test_changed_queue_digest_rejected(self):
        self.draft['source_queue_sha256'] = '0'*64
        with self.assertRaises(ValueError): check_draft_binding(self.template, self.draft)

    def test_changed_identity_rejected(self):
        self.draft['entries'][0]['decision_timestamp'] = 999
        with self.assertRaises(ValueError): check_draft_binding(self.template, self.draft)

    def test_reorder_rejected(self):
        self.draft['entries'].reverse()
        with self.assertRaises(ValueError): check_draft_binding(self.template, self.draft)

    def test_ev_ready_rejected(self):
        self.draft['ready_for_equity_or_ev'] = True
        with self.assertRaises(ValueError): check_draft_binding(self.template, self.draft)

    def test_new_root_field_rejected(self):
        self.draft['extra'] = True
        with self.assertRaises(ValueError): check_draft_binding(self.template, self.draft)


if __name__ == '__main__':
    unittest.main()
