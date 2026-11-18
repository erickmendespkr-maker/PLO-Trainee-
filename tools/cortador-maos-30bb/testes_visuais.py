# -*- coding: utf-8 -*-
"""Testes basicos para algoritmos visuais independentes de video real."""
import unittest
from PIL import Image, ImageDraw
from analise_video import parse_stack, changed_fraction, HandState


class VisualTests(unittest.TestCase):
    def test_numeros(self):
        self.assertEqual(parse_stack("R$ 1.234,50"), 1234.5)
        self.assertEqual(parse_stack("1,234.50"), 1234.5)
        self.assertEqual(parse_stack("54,75"), 54.75)
        self.assertEqual(parse_stack("100.00"), 100.0)
        self.assertIsNone(parse_stack("nada"))

    def test_carta_ausente_presente(self):
        blank = Image.new("L", (960, 540), 30)
        filled = blank.copy()
        ImageDraw.Draw(filled).rectangle([20, 20, 60, 50], fill=250)
        rect = [10, 10, 80, 65]
        reference = blank.crop(tuple(rect))
        self.assertLess(changed_fraction(blank, reference, rect), .01)
        self.assertGreater(changed_fraction(filled, reference, rect), .08)

    def test_estado_da_mao(self):
        # Este teste verifica limites sem necessidade de OCR real.
        state = HandState()
        stack = Image.new("L", (80, 30), 50)
        for t in range(3):
            state.feed(t, False, stack, 1, 1, 30, "unused")
        for t in range(3, 6):
            state.feed(t, True, stack, 1, 1, 30, "unused")
        self.assertTrue(state.active)
        self.assertEqual(state.start_at, 3)
        for t in range(6, 8):
            state.feed(t, False, stack, 1, 1, 30, "unused")
        self.assertFalse(state.active)
        self.assertIsNotNone(state.pending)
        self.assertEqual(state.pending["end"], 6)


if __name__ == "__main__":
    unittest.main()
