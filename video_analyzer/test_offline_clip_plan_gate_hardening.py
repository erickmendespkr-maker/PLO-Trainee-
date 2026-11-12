"""Regression tests for cross-platform clip filename safety."""
import unittest
from offline_clip_plan_gate import plan_clip

class ClipPlanHardeningTests(unittest.TestCase):
    def plan(self, name):
        return plan_clip('a'*64, 1, 'hand1', 1, 2, 10, 'insufficient_data', name)

    def test_valid(self):
        self.assertEqual(self.plan('hand1.mp4')['annotation'], 'INSUFFICIENT_DATA')

    def test_windows_traversal(self):
        for name in ('..\\escape.mp4', 'C:\\temp\\file.mp4', 'foo\\bar.mp4'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.plan(name)

    def test_control_character(self):
        with self.assertRaises(ValueError):
            self.plan('a\n.mp4')

    def test_long_name(self):
        with self.assertRaises(ValueError):
            self.plan('a'*130+'.mp4')

    def test_slash(self):
        with self.assertRaises(ValueError):
            self.plan('../escape.mp4')

if __name__ == '__main__':
    unittest.main()
