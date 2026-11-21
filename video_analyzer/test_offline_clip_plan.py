import unittest
from offline_clip_plan import plan_clip

class ClipPlanTests(unittest.TestCase):
    def setUp(self):
        self.hand = dict(hand_id='hand-1', table_id=2, start_seconds=10, end_seconds=20)
    def plan(self, **kw):
        return plan_clip(self.hand, source='video.mp4', destination='clip.mp4', duration_seconds=60, **kw)
    def test_padding(self):
        r=self.plan(); self.assertEqual((r['start_seconds'],r['end_seconds']),(7,23))
    def test_begin_clamp(self):
        self.hand['start_seconds']=1; self.assertEqual(self.plan()['start_seconds'],0)
    def test_end_clamp(self):
        self.hand['end_seconds']=59; self.assertEqual(self.plan()['end_seconds'],60)
    def test_no_shell(self):
        self.assertIsInstance(self.plan()['ffmpeg_argv'],list)
    def test_no_overwrite(self):
        self.assertIn('-n',self.plan()['ffmpeg_argv'])
    def test_not_verified(self):
        self.assertFalse(self.plan()['financial_result_verified'])
    def test_bad_interval(self):
        self.hand['end_seconds']=9
        with self.assertRaises(ValueError): self.plan()
    def test_nan(self):
        with self.assertRaises(ValueError): self.plan(pad_before=float('nan'))
    def test_invalid_table(self):
        self.hand['table_id']=5
        with self.assertRaises(ValueError): self.plan()
    def test_same_file(self):
        with self.assertRaises(ValueError): plan_clip(self.hand,source='same.mp4',destination='same.mp4',duration_seconds=60)
    def test_bad_extension(self):
        with self.assertRaises(ValueError): plan_clip(self.hand,source='video.exe',destination='clip.mp4',duration_seconds=60)
    def test_no_audio_optional(self):
        self.assertIn('0:a?',self.plan()['ffmpeg_argv'])

if __name__=='__main__': unittest.main()
