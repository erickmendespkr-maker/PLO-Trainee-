"""Regression checks for offline clip candidates; no live poker integrations."""
import unittest
from offline_clip_manifest import build_clip_manifest, ffmpeg_clip_arguments, manifest_json

V = "a" * 64
E = "b" * 64

def candidate(table=1, start=10, end=15, evidence=E):
    return {"table_id": table, "start_seconds": start, "end_seconds": end,
            "evidence_sha256": evidence}

class ClipManifestTests(unittest.TestCase):
    def test_valid(self):
        c = build_clip_manifest(V, 60, [candidate()])["clips"][0]
        self.assertEqual((c["start_seconds"], c["end_seconds"]), (8, 17))
        self.assertEqual(c["review_status"], "pending_human_review")

    def test_clamp(self):
        c = build_clip_manifest(V, 20, [candidate(start=0, end=20)], 3)["clips"][0]
        self.assertEqual((c["start_seconds"], c["end_seconds"]), (0, 20))

    def test_order_deterministic(self):
        a = build_clip_manifest(V, 60, [candidate(2, 20, 22), candidate(1, 10, 12)])
        b = build_clip_manifest(V, 60, [candidate(1, 10, 12), candidate(2, 20, 22)])
        self.assertEqual(manifest_json(a), manifest_json(b))

    def test_duplicate_rejected(self):
        with self.assertRaises(ValueError):
            build_clip_manifest(V, 60, [candidate(), candidate()])

    def test_invalid_tables(self):
        for table in [0, 5, True, 1.5, "1"]:
            with self.subTest(table=table), self.assertRaises(ValueError):
                build_clip_manifest(V, 60, [candidate(table=table)])

    def test_invalid_intervals(self):
        for start, end in [(2, 2), (-1, 3), (5, 61), (float("nan"), 10), (True, 10)]:
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                build_clip_manifest(V, 60, [candidate(start=start, end=end)])

    def test_invalid_hashes(self):
        with self.assertRaises(ValueError):
            build_clip_manifest("X" * 64, 60, [candidate()])
        with self.assertRaises(ValueError):
            build_clip_manifest(V, 60, [candidate(evidence="bad")])

    def test_argv_is_not_shell_command(self):
        c = build_clip_manifest(V, 60, [candidate()])["clips"][0]
        argv = ffmpeg_clip_arguments("input weird;name.mp4", "out.mp4", c)
        self.assertEqual(argv[argv.index("-i") + 1], "input weird;name.mp4")
        self.assertIn("libx264", argv)

    def test_reject_confirmed_clip(self):
        c = build_clip_manifest(V, 60, [candidate()])["clips"][0]
        c["review_status"] = "confirmed"
        with self.assertRaises(ValueError):
            ffmpeg_clip_arguments("in.mp4", "out.mp4", c)

    def test_bool_table_limit_rejected(self):
        with self.assertRaises(ValueError):
            build_clip_manifest(V, 60, [candidate()], max_tables=True)

if __name__ == "__main__":
    unittest.main()
