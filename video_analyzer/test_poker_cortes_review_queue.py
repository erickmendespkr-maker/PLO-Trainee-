import unittest
from poker_cortes_review_queue import build_review_queue

SHA = "a"*64

def candidate(**changes):
    x = dict(video_sha256=SHA, table_id=1, start_seconds=1., end_seconds=10.,
             review_status="UNVERIFIED", verified_by_human=False,
             confirmed_loss_bb=None, strategic_analysis_authorized=False,
             ocr_reported_loss_bb=35., source_rebuy_seen="NAO", source_pot_confirmed="SIM")
    x.update(changes)
    return x

class QueueTests(unittest.TestCase):
    def test_high_not_confirmed(self):
        item=build_review_queue([candidate(ocr_reported_loss_bb=320)])["items"][0]
        self.assertEqual(item["review_priority"],"HIGH")
        self.assertIsNone(item["confirmed_loss_bb"])
        self.assertFalse(item["math_analysis_authorized"])
        self.assertFalse(item["clip_loss_label_authorized"])
    def test_four_tables(self):
        r=build_review_queue([candidate(table_id=i) for i in range(1,5)])
        self.assertEqual(r["total"],4)
        self.assertEqual(len(set(x["candidate_id"] for x in r["items"])),4)
    def test_priority(self):
        r=build_review_queue([candidate(ocr_reported_loss_bb=3),candidate(table_id=2,ocr_reported_loss_bb=45)])
        self.assertEqual(r["items"][0]["table_id"],2)
    def test_rebuy(self):
        self.assertIn("REBUY_REQUIRES_SEPARATE_ACCOUNTING",build_review_queue([candidate(source_rebuy_seen="SIM")])["items"][0]["flags"])
    def test_unconfirmed_pot(self):
        self.assertIn("POT_NOT_INDEPENDENTLY_CONFIRMED",build_review_queue([candidate(source_pot_confirmed="NAO")])["items"][0]["flags"])
    def test_missing_loss(self):
        self.assertIn("LOSS_UNREADABLE",build_review_queue([candidate(ocr_reported_loss_bb=None)])["items"][0]["flags"])
    def test_duplicate(self):
        with self.assertRaises(ValueError):build_review_queue([candidate(),candidate()])
    def test_reject_promoted(self):
        for key,val in [("review_status","CONFIRMED"),("verified_by_human",True),("confirmed_loss_bb",30),("strategic_analysis_authorized",True)]:
            with self.subTest(key=key),self.assertRaises(ValueError):build_review_queue([candidate(**{key:val})])
    def test_nonfinite(self):
        for key,val in [("start_seconds",float("nan")),("end_seconds",float("inf")),("ocr_reported_loss_bb",float("nan"))]:
            with self.subTest(key=key),self.assertRaises(ValueError):build_review_queue([candidate(**{key:val})])
    def test_negative(self):
        with self.assertRaises(ValueError):build_review_queue([candidate(ocr_reported_loss_bb=-1)])
    def test_invalid_table(self):
        with self.assertRaises(ValueError):build_review_queue([candidate(table_id=5)])
    def test_invalid_hash(self):
        with self.assertRaises(ValueError):build_review_queue([candidate(video_sha256="x"*64)])
    def test_invalid_threshold(self):
        with self.assertRaises(ValueError):build_review_queue([],min_loss_bb=float("nan"))
    def test_deterministic(self):
        self.assertEqual(build_review_queue([candidate()]),build_review_queue([candidate()]))

if __name__=="__main__":unittest.main()
