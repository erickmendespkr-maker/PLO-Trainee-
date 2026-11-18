# -*- coding: utf-8 -*-
"""Testes basicos para algoritmos visuais independentes de video real."""
import csv
import io
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch
from PIL import Image, ImageDraw
from analise_video import (parse_stack, changed_fraction, HandState, bright_fraction,
                           screenshot_profile, normalize_nick, nickname_matches,
                           replicate_horizontal_rect, stack_median, MAX_STACK_BB,
                           Candidate, eligible_losses,
                           native_stack_crop, read_stack_diagnostics,
                           default_markings_path, save_markings_file, load_markings_file,
                           validated_markings,
                           net_loss_bb, loss_reaches_threshold, layout_key, mode_at,
                           layout_count, layout_bounds, layout_rect,
                           unmap_layout_rect, table_visible,
                           infer_horizontal_layout, AutoLayoutTracker)
from cortador import Video, crop_filter


class VisualTests(unittest.TestCase):
    def test_saldo_nativo_nao_perde_resolucao_do_video(self):
        picture = Image.new("RGB", (112, 44), "white")
        buffer = io.BytesIO()
        picture.save(buffer, format="PNG")
        video = Video("mock.mp4", 30, 1920, 1080, False)
        fake = SimpleNamespace(returncode=0, stdout=buffer.getvalue(), stderr=b"")
        with (patch("analise_video.file_at", return_value=(video, 2.0)),
              patch("analise_video.subprocess.run", return_value=fake) as cmd):
            cropped = native_stack_crop(
                [video], 2.0, (97, 488, 153, 510), "ffmpeg")
        self.assertEqual(cropped.size, (112, 44))
        self.assertIn("crop=112:44:194:976", cmd.call_args.args[0])

    def test_ocr_cinza_nativo_com_previa_diagnostica(self):
        picture = Image.new("RGB", (100, 25), "black")
        fake = SimpleNamespace(returncode=0, stdout="114,0\\n", stderr="")
        with patch("analise_video.subprocess.run", return_value=fake) as call:
            value, details = read_stack_diagnostics(
                picture, "tesseract", quick=True)
        self.assertEqual(value, 114.0)
        self.assertEqual(len(details), 1)
        self.assertEqual(call.call_count, 1)

    def test_quando_ocr_reduzido_falha_reler_original(self):
        pictures = [Image.new("L", (40, 20), 50) for _ in range(3)]
        state = HandState()
        state.pending = {
            "start": 10, "end": 50,
            "before": pictures, "after": pictures,
            "before_times": [8, 9, 10],
            "after_times": [50, 51, 52]}
        with patch("analise_video.stack_median",
                   side_effect=[(None, 0), (None, 0),
                                (150.0, 2), (120.0, 2)]) as reader:
            original = lambda *args: Image.new("RGB", (112, 44), "black")
            state.finish(1, 1, 30, "tesseract", quick=False,
                         native_reader=original)
        self.assertEqual(reader.call_count, 4)
        self.assertEqual(len(state.results), 1)
        self.assertEqual(state.results[0].loss_bb, 30.0)
        self.assertTrue(state.results[0].auto_verified)

    def test_ocr_nao_junta_numeros_separados(self):
        # O bug anterior transformava "154 020" em 154020 e inventava perdas.
        self.assertNotEqual(parse_stack("154 020"), 154020)
        self.assertEqual(parse_stack("114,0"), 114)
        self.assertEqual(parse_stack("200,00"), 200)

    def test_rejeitar_valor_absurdo_sem_usar_stack_fixo(self):
        images = [Image.new("L", (30, 15), 20) for _ in range(3)]
        with patch("analise_video.ocr_stack", side_effect=[154020.0, 154020.0]):
            val, count = stack_median(images[:2], "unused", quick=True, bb=1)
            self.assertIsNone(val)
            self.assertEqual(count, 0)
        with patch("analise_video.ocr_stack", side_effect=[200.0, 200.0]):
            val, count = stack_median(images[:2], "unused", quick=True, bb=1)
            self.assertEqual(val, 200)
            self.assertEqual(count, 2)
        self.assertGreater(MAX_STACK_BB, 200)

    def test_auto_verificacao_da_perda_sem_confundir_aposta(self):
        images = [Image.new("L", (30, 15), 20) for _ in range(3)]
        state = HandState()
        state.pending = {"start": 10, "end": 40,
                         "before": images, "after": images}
        with patch("analise_video.stack_median",
                   side_effect=[(150., 2), (120., 2)]):
            state.finish(1, 1, 30, "unused", quick=False)
        self.assertEqual(len(state.results), 1)
        self.assertTrue(state.results[0].auto_verified)
        self.assertEqual(state.results[0].loss_bb, 30)
        # Jogador apostou e recuperou: saldo final maior, nao e perda.
        won = HandState()
        won.pending = {"start": 40, "end": 80,
                       "before": images, "after": images}
        with patch("analise_video.stack_median",
                   side_effect=[(100., 2), (160., 2)]):
            won.finish(1, 1, 30, "unused", quick=False)
        self.assertEqual(won.results, [])

    def test_exportacao_exige_ocr_consistente_ou_confirmacao_manual(self):
        a = Candidate(0, 25, 1, 30, 100, 70, "PERDA", auto_verified=True)
        b = Candidate(25, 50, 2, 44, 150, 106, "OCR FRACO")
        c = Candidate(50, 75, 3, None, None, None, "INCONCLUSIVO")
        d = Candidate(75, 100, 4, 42, 200, 158, "MANUAL", confirmed=True)
        e = Candidate(100, 120, 1, 10, 80, 70, "PERDA", auto_verified=True)
        self.assertEqual(eligible_losses([a, b, c, d, e], 30, True), [a])
        self.assertEqual(eligible_losses([a, b, c, d, e], 30), [a, d])
        d.excluded = True
        self.assertEqual(eligible_losses([a, b, c, d, e], 30), [a])

    def test_ocr_fraco_nao_exporta_sem_conferencia(self):
        images = [Image.new("L", (30, 15), 20) for _ in range(3)]
        state = HandState()
        state.pending = {"start": 2, "end": 18,
                         "before": images, "after": images}
        with patch("analise_video.stack_median",
                   side_effect=[(200., 1), (160., 1)]):
            state.finish(1, 1, 30, "unused", quick=False)
        self.assertEqual(len(state.results), 1)
        self.assertFalse(state.results[0].auto_verified)
        self.assertEqual(eligible_losses(state.results, 30, True), [])

    def test_salvar_marcacoes_como_padrao_persiste_apos_reabrir(self):
        config = screenshot_profile()
        # Simula o usuario ajustando o nick no print.
        config["1"]["nick"] = [100, 467, 160, 489]
        config["1"]["bb"] = "2"
        with tempfile.TemporaryDirectory() as folder:
            filename = Path(folder) / "CortadorPLO" / "marcacoes_padrao.json"
            saved = save_markings_file(
                filename, config, "~Pulgar~", "Automatico (1 a 4 mesas)")
            self.assertEqual(saved, filename)
            restored = load_markings_file(filename)
            self.assertEqual(restored["nick"], "~Pulgar~")
            self.assertEqual(restored["tables"]["1"]["nick"], [100, 467, 160, 489])
            self.assertEqual(restored["tables"]["1"]["bb"], "2.0")
            self.assertEqual(restored["layout"], "Automatico (1 a 4 mesas)")
            self.assertNotIn("videos", restored)
            self.assertNotIn("timeline", restored)

    def test_configuracao_corrompida_nao_substitui_as_marcacoes(self):
        with tempfile.TemporaryDirectory() as folder:
            filename = Path(folder) / "corrompido.json"
            filename.write_text('{"tables":{"1":{}}}', encoding="utf-8")
            with self.assertRaises(ValueError):
                load_markings_file(filename)
            good = screenshot_profile()
            good["1"]["stack"] = [100, 485, 140, 505]
            save_markings_file(filename, good, "Herói", "4 lado a lado")
            self.assertEqual(
                load_markings_file(filename)["tables"]["1"]["stack"],
                [100, 485, 140, 505])

    def test_caminho_persistente_do_windows_fica_fora_do_zip(self):
        with patch.dict("os.environ", {"LOCALAPPDATA": "C:/Users/Test/AppData/Local"}):
            path = default_markings_path()
        self.assertEqual(path.name, "marcacoes_padrao.json")
        self.assertEqual(path.parent.name, "CortadorPLO")

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


    @staticmethod
    def mock_mesatela(count, present=None):
        """Desenha janelas diferentes em quantidade, com divisorias visiveis."""
        frame = Image.new("L", (960, 540), 0)
        present = set(range(1, count + 1) if present is None else present)
        pen = ImageDraw.Draw(frame)
        for table in range(1, count + 1):
            if table not in present:
                continue
            left = round(960 * (table - 1) / count)
            right = round(960 * table / count)
            width = right - left
            pen.rectangle((left+6, 12, right-7, 527), fill=45)
            pen.rectangle((left+6, 12, right-7, 60), fill=115)
            pen.ellipse((left + round(.10*width), 124,
                         right - round(.10*width), 415), fill=93)
            pen.rectangle((left + round(.38*width), 245,
                           left + round(.64*width), 279), fill=205)
            pen.rectangle((left + round(.60*width), 475,
                           left + round(.83*width), 496), fill=156)
        return frame

    def test_detector_automatico_de_varias_mesas(self):
        for count in (1, 2, 3, 4):
            image = self.mock_mesatela(count)
            detected, confidence, _scores = infer_horizontal_layout(image)
            self.assertEqual(detected, f"horizontal{count}")
            self.assertGreater(confidence, 0)

    def test_restam_tres_mesas_nas_quatro_posicoes_originais(self):
        frame = self.mock_mesatela(4, present=[1, 2, 3])
        detected, _, _ = infer_horizontal_layout(frame)
        self.assertEqual(detected, "horizontal4")
        frame = self.mock_mesatela(4, present=[3])
        detected, _, _ = infer_horizontal_layout(frame)
        self.assertEqual(detected, "horizontal4")

    def test_detector_reutiliza_inferencia_sem_duplicar_processamento(self):
        tracker = AutoLayoutTracker()
        dummy = Image.new("L", (960, 540), 40)
        with patch("analise_video.infer_horizontal_layout") as inference:
            for _ in range(3):
                mode, safe, _ = tracker.observe(
                    dummy, observation=("horizontal3", .91, {"horizontal3": .91}))
            self.assertEqual(mode, "horizontal3")
            self.assertTrue(safe)
            inference.assert_not_called()

    def test_frame_ambiguo_nao_troca_layout_imediatamente(self):
        tracker = AutoLayoutTracker()
        dummy = Image.new("L", (960, 540), 40)
        for _ in range(3):
            tracker.observe(dummy, observation=("horizontal4", .9, {}))
        mode, safe, reason = tracker.observe(
            dummy, observation=(None, 0., {}))
        self.assertEqual(mode, "horizontal4")
        self.assertFalse(safe)
        self.assertEqual(reason, "indefinido")
        mode, safe, reason = tracker.observe(
            dummy, observation=("horizontal4", .95, {}))
        self.assertEqual(mode, "horizontal4")
        self.assertTrue(safe)
        self.assertEqual(reason, "estavel")

    def test_diagnostico_gera_relatorio_csv_de_mudancas(self):
        from diagnostico_mesas import diagnosticar
        frame = self.mock_mesatela(3).tobytes()
        class FakeProcess:
            def __init__(self):
                self.stdout = io.BytesIO(frame * 3)
            def wait(self, timeout=None):
                return 0
            def poll(self):
                return 0
            def kill(self):
                pass
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "teste_mesas.csv"
            with patch("diagnostico_mesas.resource", return_value="ffmpeg"), \
                 patch("diagnostico_mesas.probe", return_value=Video("mock.mp4", 15, 960, 540, False)), \
                 patch("diagnostico_mesas.subprocess.Popen", return_value=FakeProcess()), \
                 patch("diagnostico_mesas.infer_horizontal_layout",
                       return_value=("horizontal3", .90, {"horizontal3": .90})):
                rows, stable, summary = diagnosticar("mock.mp4", path, lambda msg: None)
            self.assertEqual(rows, 3)
            self.assertEqual(stable, 1)
            with path.open(encoding="utf-8-sig", newline="") as handle:
                data = list(csv.DictReader(handle, delimiter=";"))
            self.assertEqual(len(data), 3)
            self.assertEqual(data[-1]["modo_confirmado"], "horizontal3")
            with summary.open(encoding="utf-8-sig", newline="") as handle:
                changes = list(csv.DictReader(handle, delimiter=";"))
            self.assertEqual(len(changes), 1)
            self.assertEqual(changes[0]["novo_layout"], "horizontal3")

    def test_mudanca_automatica_precisa_confirmacao_temporal(self):
        tracker = AutoLayoutTracker()
        dummy = Image.new("L", (960, 540), 40)
        with patch("analise_video.infer_horizontal_layout",
                   side_effect=[("horizontal4", .9, {})] * 3 +
                               [("horizontal3", .9, {})] * 3):
            for step in range(2):
                mode, safe, _ = tracker.observe(dummy)
                self.assertIsNone(mode)
                self.assertFalse(safe)
            mode, safe, _ = tracker.observe(dummy)
            self.assertEqual(mode, "horizontal4")
            self.assertTrue(safe)
            for step in range(2):
                mode, safe, _ = tracker.observe(dummy)
                self.assertEqual(mode, "horizontal4")
                self.assertFalse(safe)
            mode, safe, status = tracker.observe(dummy)
            self.assertEqual(mode, "horizontal3")
            self.assertTrue(safe)
            self.assertEqual(status, "alterado")

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
        self.assertFalse(table_visible(frame, layout_bounds("horizontal4", 2),
                                       strict=False))

    def test_verificacao_menos_estrita_em_layout_explicito(self):
        frame = Image.new("L", (960, 540), 36)
        # Tema diferente: muitas bordas, mas mesmo brilho medio em toda altura.
        for x in range(0, 240, 12):
            ImageDraw.Draw(frame).rectangle([x, 0, x + 5, 539], fill=76)
        bounds = layout_bounds("horizontal4", 1)
        self.assertFalse(table_visible(frame, bounds, strict=True))
        self.assertTrue(table_visible(frame, bounds, strict=False))

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
