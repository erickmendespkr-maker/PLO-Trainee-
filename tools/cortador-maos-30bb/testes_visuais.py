# -*- coding: utf-8 -*-
"""Testes basicos para algoritmos visuais independentes de video real."""
import unittest
from unittest.mock import patch
from PIL import Image, ImageDraw
from analise_video import (parse_stack, changed_fraction, HandState, bright_fraction,
                           screenshot_profile, normalize_nick, nickname_matches,
                           replicate_horizontal_rect, stack_median)


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


    def test_layout_de_quatro_colunas(self):
        from analise_video import GUI
        # Mapeamento independente da interface Tk (evita abrir janela no teste).
        dummy = type("Dummy", (), {"layout_id": lambda _self: "horizontal4"})()
        self.assertEqual(GUI.infer_table(dummy, 0, 0), 1)
        self.assertEqual(GUI.infer_table(dummy, 239, 200), 1)
        self.assertEqual(GUI.infer_table(dummy, 240, 200), 2)
        self.assertEqual(GUI.infer_table(dummy, 959, 539), 4)

    def test_copiar_area_do_saldo_entre_quatro_mesas(self):
        regions = replicate_horizontal_rect([95, 480, 152, 502], 1)
        self.assertEqual(regions[1], [95, 480, 152, 502])
        self.assertEqual(regions[2], [335, 480, 392, 502])
        self.assertEqual(regions[4], [815, 480, 872, 502])
        other = replicate_horizontal_rect([335, 480, 392, 502], 2)
        self.assertEqual(other, regions)

    def test_ocr_rapido_ler_duas_amostras(self):
        samples = [Image.new("L", (30, 15), 1) for _ in range(3)]
        with patch("analise_video.ocr_stack", return_value=95.0) as mocked:
            value, count = stack_median(samples, "unused", quick=True)
            self.assertEqual(value, 95)
            self.assertEqual(count, 2)
            self.assertEqual(mocked.call_count, 2)
        with patch("analise_video.ocr_stack", return_value=95.0) as mocked:
            value, count = stack_median(samples, "unused", quick=False)
            self.assertEqual(value, 95)
            self.assertEqual(count, 3)
            self.assertEqual(mocked.call_count, 3)

    def test_comparacao_nick(self):
        self.assertEqual(normalize_nick("~Púlgár~"), "pulgar")
        self.assertTrue(nickname_matches("Pulgar", "~Pulgar~"))
        self.assertTrue(nickname_matches("~PULGAR~", "~Pulgar~"))
        self.assertTrue(nickname_matches("Pulgar BB", "~Pulgar~"))
        self.assertFalse(nickname_matches("Jogador_Diferente", "~Pulgar~"))
        self.assertFalse(nickname_matches("", "~Pulgar~"))
        self.assertFalse(nickname_matches("ABC", ""))

    def test_perfil_hero_em_quatro_mesas(self):
        perfil = screenshot_profile()
        self.assertEqual(len(perfil), 4)
        self.assertEqual(perfil["1"]["bb"], "1")
        self.assertEqual(perfil["4"]["hole"][0] - perfil["1"]["hole"][0], 720)
        self.assertEqual(perfil["3"]["detector"], "bright")
        for table in range(1, 5):
            hole = perfil[str(table)]["hole"]
            stack = perfil[str(table)]["stack"]
            nick = perfil[str(table)]["nick"]
            self.assertLess(nick[0], nick[2])
            self.assertLess(nick[2], 961)
            self.assertLess(hole[0], hole[2])
            self.assertLess(hole[2], 961)
            self.assertLess(stack[3], 541)

    def test_detectar_cartas_sem_referencia_manual(self):
        perfil = screenshot_profile()["1"]
        image = Image.new("L", (960, 540), 40)
        self.assertLess(bright_fraction(image, perfil["hole"]), .02)
        ImageDraw.Draw(image).rectangle(perfil["hole"], fill=245)
        self.assertGreater(bright_fraction(image, perfil["hole"]), .95)

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
