# -*- coding: utf-8 -*-
"""Testes basicos do recorte e do parser. Executar: py -3 testes.py"""
import tempfile
import unittest
from pathlib import Path
from cortador import Video, Clip, parse_hand, split_history, parse_time, crop_filter, file_at

SAMPLE = """PokerStars Hand #12345678: Omaha Pot Limit ($0.50/$1.00 USD) - 2026/11/17 20:04:04 BRT
Table 'Manga' 6-max Seat #1 is the button
Seat 1: ~Pulgar~ ($100.00 in chips)
*** HOLE CARDS ***
Dealt to ~Pulgar~ [Ah Kh Qh Jh 9d]
~Pulgar~: posts big blind $1.00
Adversario: raises $2.00 to $3.00
~Pulgar~: calls $2.00
*** FLOP *** [2c 7d Jd]
~Pulgar~: checks
Adversario: bets $35.00
~Pulgar~: calls $35.00
*** TURN *** [2c 7d Jd] [8h]
~Pulgar~: folds
*** SUMMARY ***
Total pot $76.00 | Rake $0.00
Seat 1: ~Pulgar~ (big blind) folded on the Turn
"""

class Tests(unittest.TestCase):
    def test_loss_accounting(self):
        h = parse_hand(SAMPLE, "~Pulgar~")
        self.assertIsNotNone(h)
        self.assertEqual(h.bb, 1)
        self.assertAlmostEqual(h.net, -38)
        self.assertAlmostEqual(h.loss_bb, 38)
        self.assertEqual(h.timestamp, "2026-11-17 20:04:04")

    def test_raise_increment(self):
        src = SAMPLE.replace("~Pulgar~: calls $2.00", "~Pulgar~: raises $4.00 to $5.00")
        h = parse_hand(src, "~Pulgar~")
        self.assertAlmostEqual(h.net, -40) # 1 + (5-1) + 35

    def test_multi_hands(self):
        self.assertEqual(len(split_history(SAMPLE + "\n" + SAMPLE)), 2)

    def test_time(self):
        self.assertEqual(parse_time("01:30"), 90)
        self.assertEqual(parse_time("01:01:30"), 3690)

    def test_quadrants(self):
        v = Video("demo.mp4", 100, 1920, 1080, True)
        self.assertTrue(crop_filter(v, 4).startswith("crop=960:540:960:540"))

    def test_horizontal_four_tables(self):
        v = Video("demo.mp4", 100, 1920, 1080, True)
        self.assertTrue(crop_filter(v, 1, "horizontal4").startswith("crop=480:1080:0:0"))
        self.assertTrue(crop_filter(v, 4, "horizontal4").startswith("crop=480:1080:1440:0"))

    def test_sequential_videos(self):
        a = Video("a.mp4", 100, 1920, 1080, True, 0)
        b = Video("b.mp4", 200, 1920, 1080, False, 100)
        self.assertEqual(file_at([a, b], 125)[1], 25)


if __name__ == "__main__":
    unittest.main()
