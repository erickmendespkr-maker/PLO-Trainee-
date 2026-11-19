import unittest
from video_analyzer.offline_confirmed_hand_intervals import build_intervals

SHA = "a"*64
def event(table,pts,decision,verified=True):
    return {"table_id":table,"candidate_pts_seconds":pts,"review_status":"HUMAN_REVIEWED",
            "reviewer_decision":{"decision":decision},"hand_boundary_verified":verified}
class TestIntervals(unittest.TestCase):
    def test_pair(self):
        result=build_intervals({"schema_version":1,"source_video_sha256":SHA,"items":[event(1,10,"CONFIRMED_HAND_START"),event(1,25,"CONFIRMED_HAND_END")]},30)
        self.assertEqual(result["intervals"][0]["duration_seconds"],15)
        self.assertEqual(result["intervals"][0]["cards_status"],"UNVERIFIED")
    def test_multitable(self):
        items=[event(1,1,"CONFIRMED_HAND_START"),event(2,2,"CONFIRMED_HAND_START"),event(1,5,"CONFIRMED_HAND_END"),event(2,6,"CONFIRMED_HAND_END")]
        self.assertEqual(len(build_intervals({"schema_version":1,"source_video_sha256":SHA,"items":items})["intervals"]),2)
    def test_unpaired(self):
        result=build_intervals({"schema_version":1,"source_video_sha256":SHA,"items":[event(1,10,"CONFIRMED_HAND_START")]})
        self.assertEqual(result["unresolved_boundaries"][0]["reason"],"START_WITHOUT_END")
    def test_reject_unverified(self):
        with self.assertRaises(ValueError):
            build_intervals({"schema_version":1,"source_video_sha256":SHA,"items":[event(1,10,"CONFIRMED_HAND_START",False)]})
    def test_duplicate(self):
        e=event(1,10,"CONFIRMED_HAND_START")
        with self.assertRaises(ValueError):
            build_intervals({"schema_version":1,"source_video_sha256":SHA,"items":[e,e]})
    def test_outside_duration(self):
        with self.assertRaises(ValueError):
            build_intervals({"schema_version":1,"source_video_sha256":SHA,"items":[event(1,31,"CONFIRMED_HAND_START")]},30)
if __name__=="__main__": unittest.main()
