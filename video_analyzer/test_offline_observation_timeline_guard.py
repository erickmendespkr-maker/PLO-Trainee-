import unittest
from offline_observation_timeline_guard import validate_observation_timeline as check

def obs(pts, street, board=None, **kw):
    return {**dict(table_id=1, hand_id="h1", pts_s=pts, street=street, board=board, verified_by_human=False), **kw}

class TimelineTests(unittest.TestCase):
    def test_valid(self):
        self.assertTrue(check([obs(1,"flop",["As","Kd","2c"]),obs(2,"turn",["As","Kd","2c","3h"])],duration_s=10)["ok"])
    def test_regression(self):
        self.assertIn("STREET_REGRESSION",[e["code"] for e in check([obs(1,"river"),obs(2,"flop")],duration_s=10)["errors"]])
    def test_changed_board(self):
        self.assertIn("BOARD_CHANGED",[e["code"] for e in check([obs(1,"flop",["As","Kd","2c"]),obs(2,"turn",["As","Qd","2c","3h"])],duration_s=10)["errors"]])
    def test_missing_board_allowed(self):
        self.assertTrue(check([obs(1,"flop"),obs(2,"turn")],duration_s=10)["ok"])
    def test_bad_board(self):
        self.assertFalse(check([obs(1,"flop",["As","As","2c"])],duration_s=10)["ok"])
    def test_no_human_promotion(self):
        a=obs(1,"flop");a["verified_by_human"]=True
        self.assertIn("UNSAFE_VERIFICATION",[e["code"] for e in check([a],duration_s=10)["errors"]])
    def test_bad_pts(self):
        self.assertFalse(check([obs(float("nan"),"flop")],duration_s=10)["ok"])
    def test_bad_table(self):
        self.assertFalse(check([obs(1,"flop",table_id=5)],duration_s=10)["ok"])
    def test_duplicate_pts(self):
        self.assertFalse(check([obs(1,"flop"),obs(1,"turn")],duration_s=10)["ok"])
    def test_separate_hands(self):
        a=obs(1,"river");b=obs(2,"flop");b["hand_id"]="h2"
        self.assertTrue(check([a,b],duration_s=10)["ok"])
    def test_invalid_duration(self):
        with self.assertRaises(ValueError): check([],duration_s=float("inf"))

if __name__=="__main__":
    unittest.main()
