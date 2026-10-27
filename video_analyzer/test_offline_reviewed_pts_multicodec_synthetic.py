"""Synthetic FFmpeg/FFprobe PTS regression: H.264 CFR and VP9 VFR, no poker content."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from offline_reviewed_source_pts_audit import _scan_pts


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),
                     "FFmpeg and FFprobe required")
class MultiCodecPTSTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def make_video(self, filename, codec, vfr):
        output = self.root / filename
        filters = ["drawbox=x=0:y=0:w=80:h=45:color=red@0.2:t=fill",
                   "drawbox=x=80:y=0:w=80:h=45:color=green@0.2:t=fill",
                   "drawbox=x=0:y=45:w=80:h=45:color=blue@0.2:t=fill",
                   "drawbox=x=80:y=45:w=80:h=45:color=yellow@0.2:t=fill"]
        if vfr:
            filters.insert(0, "select='not(mod(n,4))'")
        command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin",
                   "-f", "lavfi", "-i", "testsrc2=size=160x90:rate=8:duration=4",
                   "-vf", ",".join(filters), "-fps_mode", "vfr" if vfr else "cfr",
                   "-an", "-c:v", codec]
        if codec == "libx264":
            command += ["-preset", "ultrafast", "-crf", "35", "-pix_fmt", "yuv420p"]
        else:
            command += ["-deadline", "realtime", "-cpu-used", "8", "-b:v", "150k"]
        command += [str(output)]
        proc = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              timeout=30, check=False)
        if proc.returncode != 0 and b"Unknown encoder" in proc.stderr:
            self.skipTest(f"{codec} encoder not installed")
        self.assertEqual(proc.returncode, 0, proc.stderr.decode(errors="replace"))
        return output

    def test_h264_constant_frame_rate_four_visual_regions(self):
        path = self.make_video("four_regions.mp4", "libx264", False)
        points = [{"human_seconds": 1.25}, {"human_seconds": 3.0}]
        scan = _scan_pts(path, points, "ffprobe", 30, 100)
        self.assertEqual(scan["decoded_frames_scanned"], 32)
        self.assertAlmostEqual(points[0]["nearest_decoded_pts_seconds"], 1.25, places=3)
        self.assertEqual(points[0]["absolute_delta_seconds"], 0)

    def test_vp9_variable_frame_rate_reports_gap(self):
        path = self.make_video("four_regions.webm", "libvpx-vp9", True)
        points = [{"human_seconds": 1.2}, {"human_seconds": 3.0}]
        scan = _scan_pts(path, points, "ffprobe", 30, 100)
        self.assertEqual(scan["decoded_frames_scanned"], 8)
        self.assertAlmostEqual(points[0]["nearest_decoded_pts_seconds"], 1.0, places=2)
        self.assertGreater(points[0]["absolute_delta_seconds"], 0.15)


if __name__ == "__main__":
    unittest.main()
