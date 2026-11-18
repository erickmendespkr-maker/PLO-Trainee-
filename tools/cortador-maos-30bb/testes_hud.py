# -*- coding: utf-8 -*-
"""Testes locais sem video real, rede ou Tesseract instalado."""
import unittest
from unittest.mock import patch
from PIL import Image

from analise_video import parse_stack, nickname_matches
from hud_recognition import (
    is_full_hud, hud_balance_from_text, hud_search_regions,
    read_hud_nick, read_hud_stack,
)


class HUDRecognitionTests(unittest.TestCase):
    def test_ler_125_7_bb_sem_confundir_cartas(self):
        text = "A K 6 4 7\n~Pulgar~\n125,7 BB\nCarta alta"
        self.assertEqual(hud_balance_from_text(text, parse_stack), 125.7)
        self.assertEqual(hud_balance_from_text("127.7BB", parse_stack), 127.7)
        self.assertIsNone(hud_balance_from_text("A K 6 125,7 Carta alta", parse_stack))
        self.assertIsNone(hud_balance_from_text("99 BB\n125 BB", parse_stack))

    def test_read_stack_recebe_hud_inteiro(self):
        full = Image.new("RGB", (210, 125), "black")
        self.assertTrue(is_full_hud(full))
        with patch("hud_recognition._ocr",
                   side_effect=["~Pulgar~\n125,7 BB"]) as mock:
            amount, details = read_hud_stack(
                full, "unused", parse_stack, quick=True)
        self.assertEqual(amount, 125.7)
        self.assertEqual(details[0][0], "hud_inteiro")
        self.assertEqual(mock.call_count, 1)

    def test_regioes_internas_sao_buscas_na_caixa_grande(self):
        full = Image.new("RGB", (210, 125), "black")
        regions = hud_search_regions(full)
        self.assertEqual(regions[0][1].size, (210, 125))
        for name, image in regions:
            self.assertTrue(5 < image.width <= 210)
            self.assertTrue(5 < image.height <= 125)

    def test_nick_procurado_em_linhas_do_hud(self):
        full = Image.new("RGB", (200, 120), "black")
        with patch("hud_recognition._ocr",
                   side_effect=[
                       "AQJ65\n~Pulgar~\n99,0 BB\nCarta alta",
                       "~Pulgar~\n99,0 BB", ""
                   ]):
            readings = read_hud_nick(full, "unused")
        self.assertTrue(any(nickname_matches(line, "~Pulgar~")
                            for line in readings))

    def test_recorte_antigo_pequeno_nao_e_tratado_como_hud(self):
        self.assertFalse(is_full_hud(Image.new("L", (68, 18), 0)))


if __name__ == "__main__":
    unittest.main()
