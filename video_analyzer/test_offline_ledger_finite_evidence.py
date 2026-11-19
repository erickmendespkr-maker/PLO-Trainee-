"""Regression tests for non-finite and invalid offline ledger evidence."""
import copy
import math
import unittest
from offline_proposal_review_ledger import build_review_ledger
from offline_review_ledger_io import validate_ledger

def sample():
    return build_review_ledger({
        "schema_version": 1, "analysis_verified": False,
        "hand_boundaries_verified": False,
        "proposals": [{
            "table_id": 1, "start_observed_seconds": 1,
            "end_observed_seconds": 2, "sample_count": 2,
            "minimum_confidence": 0.8,
            "board_states_observed": ["flop", "turn"],
            "hand_verified": False, "boundaries_verified": False
        }]
    }, video_sha256="a"*64, duration_seconds=60)

class LedgerFiniteEvidenceTests(unittest.TestCase):
    def test_valid(self):
        self.assertTrue(validate_ledger(sample()))

    def test_nan_start(self):
        item=sample()
        item["entries"][0]["start_observed_seconds"]=math.nan
        with self.assertRaises(ValueError): validate_ledger(item)

    def test_nan_end(self):
        item=sample()
        item["entries"][0]["end_observed_seconds"]=math.nan
        with self.assertRaises(ValueError): validate_ledger(item)

    def test_infinite_end(self):
        item=sample()
        item["entries"][0]["end_observed_seconds"]=math.inf
        with self.assertRaises(ValueError): validate_ledger(item)

    def test_negative_infinite_start(self):
        item=sample()
        item["entries"][0]["start_observed_seconds"]=-math.inf
        with self.assertRaises(ValueError): validate_ledger(item)

    def test_boolean_timestamp(self):
        item=sample()
        item["entries"][0]["start_observed_seconds"]=False
        with self.assertRaises(ValueError): validate_ledger(item)

    def test_unverified_not_promoted(self):
        item=sample()
        item["entries"][0]["clip_export_allowed"]=True
        with self.assertRaises(ValueError): validate_ledger(item)

if __name__=="__main__":
    unittest.main()
