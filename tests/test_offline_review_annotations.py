"""Regression tests for offline review annotation validation."""
import copy
import unittest
from video_analyzer.offline_review_annotations import validate_annotations

SHA = "a" * 64
BASE = {"video_sha256": SHA, "duration_seconds": 3600, "observations": [{
    "table_id": 1, "hand_id": "h1", "timestamp_seconds": 10.25,
    "field": "pot", "raw_text": "12O", "corrected_value": None,
    "confidence": 0.65, "reviewed_by_human": False, "frame_sha256": SHA
}]}


class ReviewAnnotationTests(unittest.TestCase):
    def test_unreviewed_never_authorizes_ev(self):
        result = validate_annotations(BASE)
        self.assertFalse(result["ev_authorized"])
        self.assertEqual(result["unreviewed_count"], 1)

    def test_reviewed_field_still_does_not_authorize_ev(self):
        value = copy.deepcopy(BASE)
        value["observations"][0].update(reviewed_by_human=True, corrected_value="120")
        self.assertEqual(validate_annotations(value)["reviewed_count"], 1)
        self.assertFalse(validate_annotations(value)["ev_authorized"])

    def test_review_requires_correction(self):
        value = copy.deepcopy(BASE)
        value["observations"][0]["reviewed_by_human"] = True
        with self.assertRaises(ValueError):
            validate_annotations(value)

    def test_duplicate_evidence_rejected(self):
        value = copy.deepcopy(BASE)
        value["observations"].append(copy.deepcopy(value["observations"][0]))
        with self.assertRaises(ValueError):
            validate_annotations(value)

    def test_invalid_observation_fields(self):
        for key, bad in [
            ("table_id", 5), ("timestamp_seconds", 3601),
            ("confidence", float("nan")), ("field", "hidden_cards"),
            ("frame_sha256", "bad"), ("reviewed_by_human", 1),
        ]:
            with self.subTest(key=key):
                value = copy.deepcopy(BASE)
                value["observations"][0][key] = bad
                with self.assertRaises(ValueError):
                    validate_annotations(value)

    def test_invalid_document(self):
        for key, bad in [
            ("video_sha256", "x"), ("duration_seconds", True),
            ("duration_seconds", float("inf")), ("observations", {}),
        ]:
            with self.subTest(key=key):
                value = copy.deepcopy(BASE)
                value[key] = bad
                with self.assertRaises(ValueError):
                    validate_annotations(value)

    def test_empty_observations(self):
        value = copy.deepcopy(BASE)
        value["observations"] = []
        self.assertEqual(validate_annotations(value)["reviewed_count"], 0)


if __name__ == "__main__":
    unittest.main()
