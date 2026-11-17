"""Regression: nearby keyframes must not count as frames inside the crop interval."""
import json
import unittest
from unittest.mock import patch
from types import SimpleNamespace

try:
    from .offline_table_crop_audit import _source_has_frame
except ImportError:
    from offline_table_crop_audit import _source_has_frame


class StrictCropPTSRegression(unittest.TestCase):
    def _probe(self, timestamps):
        output = json.dumps({"frames": [
            {"best_effort_timestamp_time": str(value)} for value in timestamps
        ]})
        with patch("subprocess.run", return_value=SimpleNamespace(stdout=output)) as run, \
             patch(_source_has_frame.__module__ + "._source_duration", return_value=10):
            result = _source_has_frame("synthetic.mp4", 5.0, 1.0)
        self.assertIn("-read_intervals", run.call_args.args[0])
        return result

    def test_keyframe_before_start_is_not_proof(self):
        self.assertFalse(self._probe([4.8]))

    def test_frame_inside_interval_is_proof(self):
        self.assertTrue(self._probe([4.8, 5.2]))

    def test_frame_after_end_is_not_proof(self):
        self.assertFalse(self._probe([6.3]))

    def test_missing_or_invalid_pts_is_not_proof(self):
        self.assertFalse(self._probe(["nan", "garbage"]))


if __name__ == "__main__":
    unittest.main()
