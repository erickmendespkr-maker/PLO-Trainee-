import copy
import unittest
from offline_review_ledger import append_event, verify

BASE = {'video_sha256': 'a'*64, 'hand_id': 'hand-1', 'table_id': 2, 'pts_seconds': 12.5, 'kind': 'ocr_proposal', 'payload': {'pot': '10'}}

class LedgerTests(unittest.TestCase):
    def test_append_verify(self):
        events = append_event([], BASE)
        self.assertTrue(verify(events))
        self.assertEqual(events, append_event([], BASE))
        self.assertTrue(verify(append_event(events, {**BASE, 'kind':'human_correction'})))
    def test_tamper(self):
        events = append_event([], BASE)
        changed = copy.deepcopy(events)
        changed[0]['event']['payload']['pot'] = '100'
        self.assertFalse(verify(changed))
        with self.assertRaises(ValueError): append_event(changed, BASE)
    def test_bad_inputs(self):
        for event in ({**BASE, 'table_id':5}, {**BASE, 'pts_seconds':float('nan')}, {**BASE, 'kind':'ocr_proposal', 'payload':{'confirmed':True}}, {**BASE, 'video_sha256':'x'*64}, {**BASE, 'table_id':True}):
            with self.subTest(event=event), self.assertRaises(ValueError): append_event([], event)
    def test_nonfinite_payload(self):
        with self.assertRaises(ValueError): append_event([], {**BASE, 'payload': {'x':float('nan')}})

if __name__ == '__main__': unittest.main()
