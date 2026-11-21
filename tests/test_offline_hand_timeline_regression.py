"""Regression tests for conservative offline hand timeline proposals."""
import unittest
from video_analyzer.offline_hand_timeline import Observation, propose_intervals

def o(t=1, street="flop", board=("As","Kd","Qc"), confidence=0.8, table="1"):
    return Observation(table_id=table, timestamp=t, street=street, board=board, confidence=confidence)

class OfflineHandTimelineTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(propose_intervals([], 10), [])
    def test_board_change_is_not_confirmed(self):
        result = propose_intervals([o(), o(t=2, board=("As","Kd","Jc"))], 10)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["reason"], "board_change")
        self.assertFalse(result[0]["boundary_exact"])
        self.assertFalse(result[0]["verified_by_human"])
        self.assertIsNone(result[0]["hand_id"])
    def test_street_reset(self):
        result = propose_intervals([o(street="river", board=("As","Kd","Qc","2h","3d")), o(t=2, street="preflop", board=())], 10)
        self.assertEqual(result[0]["reason"], "street_reset")
    def test_same_state_no_proposal(self):
        self.assertEqual(propose_intervals([o(), o(t=2)], 10), [])
    def test_confidence_upper_bound(self):
        result = propose_intervals([o(confidence=0.9), o(t=2, confidence=0.3, board=("As","Kd","Jc"))], 10)
        self.assertEqual(result[0]["confidence_upper_bound"], 0.3)
    def test_out_of_order(self):
        a = [o(t=2, board=("As","Kd","Jc")), o()]
        self.assertEqual(propose_intervals(a, 10), propose_intervals(a[::-1], 10))
    def test_tables_isolated(self):
        self.assertEqual(propose_intervals([o(table="1"), o(t=2, table="2")], 10), [])
    def test_duplicate_timestamp_rejected(self):
        with self.assertRaises(ValueError):
            propose_intervals([o(), o()], 10)
    def test_timestamp_outside_video(self):
        with self.assertRaises(ValueError):
            propose_intervals([o(t=11)], 10)
    def test_invalid_confidence(self):
        with self.assertRaises(ValueError):
            propose_intervals([o(confidence=1.5)], 10)
    def test_invalid_board_length(self):
        with self.assertRaises(ValueError):
            propose_intervals([o(board=("As",))], 10)
    def test_invalid_street(self):
        with self.assertRaises(ValueError):
            propose_intervals([o(street="showdown")], 10)
    def test_invalid_duration(self):
        with self.assertRaises(ValueError):
            propose_intervals([], 0)

if __name__ == "__main__":
    unittest.main()
