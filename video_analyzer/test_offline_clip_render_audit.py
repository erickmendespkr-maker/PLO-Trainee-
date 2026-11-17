import unittest
from offline_clip_render_audit import audit_render
C = {"clip_id":"abc","start_seconds":1.0,"end_seconds":3.0,
     "review_status":"pending_human_review",
     "strategic_analysis_status":"insufficient_verified_evidence"}
P = {"format":{"duration":"2.000"},"streams":[{"codec_type":"video","width":320,"height":240}]}
class TestRenderAudit(unittest.TestCase):
    def test_valid(self): self.assertFalse(audit_render(C,P)["content_verified"])
    def test_mismatch(self):
        with self.assertRaises(ValueError): audit_render(C,{**P,"format":{"duration":"3"}})
    def test_no_stream(self):
        with self.assertRaises(ValueError): audit_render(C,{**P,"streams":[]})
    def test_missing_duration(self):
        with self.assertRaises(ValueError): audit_render(C,{**P,"format":{}})
    def test_nan(self):
        with self.assertRaises(ValueError): audit_render(C,{**P,"format":{"duration":"nan"}})
    def test_bool_timestamp(self):
        with self.assertRaises(ValueError): audit_render({**C,"start_seconds":False},P)
    def test_review(self):
        with self.assertRaises(ValueError): audit_render({**C,"review_status":"approved"},P)
    def test_strategy(self):
        with self.assertRaises(ValueError): audit_render({**C,"strategic_analysis_status":"verified"},P)
    def test_tolerance(self): self.assertTrue(audit_render(C,{**P,"format":{"duration":"2.1"}})["video_stream_present"])
    def test_negative_tolerance(self):
        with self.assertRaises(ValueError): audit_render(C,P,tolerance_seconds=-1)
if __name__ == "__main__": unittest.main()
