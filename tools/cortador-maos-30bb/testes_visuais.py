# -*- coding: utf-8 -*-
"""Testes basicos para algoritmos visuais independentes de video real."""
import unittest
from unittest.mock import patch
from PIL import Image, ImageDraw
from analise_video import (parse_stack, changed_fraction, HandState, bright_fraction,
                           screenshot_profile, normalize_nick, nickname_matches,
                           replicate_horizontal_rect, stack_median,
                           net_loss_bb, loss_reaches_threshold, layout_key, mode_at,
                           layout_count, layout_bounds, layout_rect,
                           unmap_layout_rect, table_visible)
from cortador import Video, crop_filter


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


    def test_layout_variavel_de_uma_a_quatro_mesas(self):
        self.assertEqual(layout_key("Auto (ate 4, slots fixos)"), "auto4")
        self.assertEqual(layout_count("1 mesa"), 1)
        self.assertEqual(layout_count("2 lado a lado"), 2)
        self.assertEqual(layout_count("3 lado a lado"), 3)
        self.assertEqual(layout_count("4 lado a lado"), 4)
        self.assertEqual(layout_bounds("horizontal3", 1), (0, 0, 320, 540))
        self.assertEqual(layout_bounds("horizontal3", 3), (640, 0, 960, 540))
        self.assertEqual(layout_bounds("horizontal2", 2), (480, 0, 960, 540))
        with self.assertRaises(ValueError):
            layout_bounds("horizontal3", 4)

    def test_linha_do_tempo_quatro_para_tres_para_duas(self):
        events = [
            {"start": 600, "layout": "3 lado a lado"},
            {"start": 1200, "layout": "2 lado a lado"}
        ]
        self.assertEqual(mode_at(0, "4 lado a lado", events), "horizontal4")
        self.assertEqual(mode_at(599, "4 lado a lado", events), "horizontal4")
        self.assertEqual(mode_at(600, "4 lado a lado", events), "horizontal3")
        self.assertEqual(mode_at(1199, "4 lado a lado", events), "horizontal3")
        self.assertEqual(mode_at(1200, "4 lado a lado", events), "horizontal2")

    def test_regioes_escaladas_por_mesa(self):
        profile = screenshot_profile()
        for count in (1, 2, 3, 4):
            mode = f"horizontal{count}"
            for table in range(1, count + 1):
                for name in ("hole", "stack", "nick"):
                    source = profile[str(table)][name]
                    mapped = layout_rect(source, table, mode)
                    bounds = layout_bounds(mode, table)
                    self.assertTrue(bounds[0] <= mapped[0] < mapped[2] <= bounds[2])
                    self.assertTrue(bounds[1] <= mapped[1] < mapped[3] <= bounds[3])
                    back = unmap_layout_rect(mapped, table, mode)
                    self.assertLessEqual(max(abs(a-b) for a, b in zip(source, back)), 1)

    def test_mesa_vazia_nao_conta_como_mesa_ativa(self):
        frame = Image.new("L", (960, 540), 0)
        self.assertFalse(table_visible(frame, layout_bounds("horizontal4", 1)))
        # Simula uma mesa somente no primeiro slot, sem OCR.
        ImageDraw.Draw(frame).rectangle([5, 150, 234, 450], fill=105)
        self.assertTrue(table_visible(frame, layout_bounds("horizontal4", 1)))
        self.assertFalse(table_visible(frame, layout_bounds("horizontal4", 2)))

    def test_corte_com_quantidade_variavel_de_mesas(self):
        video = Video("mock.mp4", 100.0, 1920, 1080, True)
        self.assertTrue(crop_filter(video, 3, "horizontal3").startswith(
            "crop=640:1080:1280:0"))
        self.assertTrue(crop_filter(video, 2, "horizontal2").startswith(
            "crop=960:1080:960:0"))
        self.assertTrue(crop_filter(video, 1, "horizontal1").startswith(
            "crop=1920:1080:0:0"))
        with self.assertRaises(ValueError):
            crop_filter(video, 4, "horizontal3")

    def test_layout_de_quatro_colunas(self):
        from analise_video import GUI
        # Mapeamento independente da interface Tk (evita abrir janela no teste).
        dummy = type("Dummy", (), {"layout_id": lambda _self: "horizontal4"})()
        self.assertEqual(GUI.infer_table(dummy, 0, 0), 1)
        self.assertEqual(GUI.infer_table(dummy, 239, 200), 1)
        self.assertEqual(GUI.infer_table(dummy, 240, 200), 2)
        self.assertEqual(GUI.infer_table(dummy, 959, 539), 4)

    def test_perda_inclusiva_e_stack_variavel(self):
        # Stack inicial nao e fixo em 100 BB e perdas exatas de 30 entram.
        for before, after in ((100, 70), (150, 120), (200, 170), (75, 45)):
            loss = net_loss_bb(before, after, 1)
            self.assertEqual(loss, 30)
            self.assertTrue(loss_reaches_threshold(loss, 30))
        self.assertFalse(loss_reaches_threshold(net_loss_bb(200, 170.1, 1), 30))
        self.assertTrue(loss_reaches_threshold(net_loss_bb(200, 160, 1), 30))
        self.assertFalse(loss_reaches_threshold(net_loss_bb(150, 175, 1), 30))
        # Quando stack e exibido em fichas, converte para BB.
        self.assertTrue(loss_reaches_threshold(net_loss_bb(200, 140, 2), 30))

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
