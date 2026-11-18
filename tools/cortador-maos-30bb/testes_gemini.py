# -*- coding: utf-8 -*-
"""Testes do backend Gemini; nunca fazem chamadas reais e nao usam uma chave real."""
import io
import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image

from gemini_backend import (
    GeminiClient, GeminiLimitError, DEFAULT_MODEL,
    interpret_stack_response, normalize_amount, stable_pair,
    read_key,
    save_key,
)
from analise_video import (HandState, Candidate, screenshot_profile,
                            recheck_sample_times, recheck_candidates_with_gemini)
from cortador import Video


class FakeResponse:
    def __init__(self, data):
        self._data = data

    def read(self):
        return json.dumps(self._data).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def fake_api_payload(before=None, after=None):
    body = {"before": before or [150, 150],
            "after": after or [110, 110]}
    return {"candidates": [{"content": {
        "parts": [{"text": json.dumps(body)}]}}]}


class GeminiTests(unittest.TestCase):
    def test_recuperar_maos_de_revisao_anterior_sem_revarrer_mp4(self):
        import types
        video = Video("gravacao.mp4", 180.0, 1920, 1080, True)
        candidate = Candidate(
            5, 45, 1, None, None, None,
            "INCONCLUSIVO - SALDO NAO LIDO",
            layout="horizontal4", before_times=[3, 5],
            after_times=[40, 42])
        class StubGemini:
            disabled_reason = None
            limit = 1
            used = 0
            def read_pair(self, before, after, bb, max_stack_bb):
                self.used += 1
                assert len(before) == len(after) == 2
                return 150.0, 120.0
        client = StubGemini()
        image = Image.new("RGB", (112, 44), "black")
        with patch("analise_video.resource", return_value="ffmpeg"), \
             patch("analise_video.native_stack_crop", return_value=image) as crop:
            result, inspected, positives = recheck_candidates_with_gemini(
                [video], screenshot_profile(), [candidate], 30, client)
        self.assertEqual(inspected, 1)
        self.assertEqual(positives, 1)
        self.assertTrue(result[0].auto_verified)
        self.assertTrue(result[0].gemini_checked)
        self.assertEqual(result[0].loss_bb, 30.0)
        self.assertEqual(result[0].source, "Gemini")
        self.assertEqual(crop.call_count, 4)
        # A segunda reanalise nao cobra a mesma pendencia novamente.
        with patch("analise_video.native_stack_crop") as again:
            result2, inspected2, positives2 = recheck_candidates_with_gemini(
                [video], screenshot_profile(), result, 30, client)
        self.assertEqual((inspected2, positives2), (0, 0))
        again.assert_not_called()

    def test_recuperacao_pode_usar_tempos_da_revisao_antiga(self):
        item = Candidate(20, 80, 1, None, None, None,
                         "INCONCLUSIVO - SALDO NAO LIDO")
        times = recheck_sample_times(item, 180)
        self.assertEqual(times, ([21, 23], [76, 78]))
        item.before_times = [16, 18, 19]
        item.after_times = [82, 83, 84]
        self.assertEqual(recheck_sample_times(item, 180),
                         ([18, 19], [83, 84]))

    def test_reanalise_nao_exporta_aposta_recuperada(self):
        video = Video("gravacao.mp4", 100.0, 1920, 1080, True)
        candidate = Candidate(
            5, 45, 1, None, None, None,
            "INCONCLUSIVO - SALDO NAO LIDO",
            layout="horizontal4", before_times=[3, 5],
            after_times=[40, 42])
        client = Mock()
        client.disabled_reason = None
        client.used = 0
        client.limit = 2
        client.read_pair.return_value = (100.0, 110.0)
        image = Image.new("RGB", (112, 44), "black")
        with patch("analise_video.resource", return_value="ffmpeg"), \
             patch("analise_video.native_stack_crop", return_value=image):
            revised, checked, positives = recheck_candidates_with_gemini(
                [video], screenshot_profile(), [candidate], 30, client)
        self.assertEqual((checked, positives), (1, 0))
        self.assertTrue(revised[0].excluded)
        self.assertFalse(revised[0].auto_verified)

    def test_numeros_sem_inventar_decimais(self):
        self.assertEqual(normalize_amount("114,0"), 114)
        self.assertIsNone(normalize_amount("114 BB"))
        self.assertIsNone(normalize_amount("114 e 80"))
        self.assertIsNone(normalize_amount(None))
        self.assertIsNone(normalize_amount(15000))
        self.assertIsNone(stable_pair([150, 99]))
        self.assertEqual(stable_pair([150, 150.2]), 150.1)

    def test_exige_duas_leituras_antes_e_depois(self):
        self.assertEqual(interpret_stack_response({
            "before": [200, "200,0"],
            "after": [170, 170],
        }), (200, 170))
        self.assertIsNone(interpret_stack_response({
            "before": [150, None], "after": [110, 110]
        }))
        self.assertIsNone(interpret_stack_response({
            "before": [150, 150], "after": [110, 700]
        }))
        self.assertIsNone(interpret_stack_response({
            "before": [150], "after": [110, 110]
        }))

    def test_enviar_quatro_recortes_e_respeitar_limite(self):
        requests = []
        def transport(request, timeout):
            requests.append(request)
            self.assertEqual(timeout, 45)
            self.assertEqual(request.headers["X-goog-api-key"], "EXAMPLE_NOT_REAL_KEY")
            payload = json.loads(request.data.decode("utf-8"))
            parts = payload["contents"][0]["parts"]
            images = [p for p in parts if "inline_data" in p]
            self.assertEqual(len(images), 4)
            return FakeResponse(fake_api_payload())

        client = GeminiClient("EXAMPLE_NOT_REAL_KEY", model=DEFAULT_MODEL,
                              max_requests=1, transport=transport)
        image = Image.new("RGB", (48, 24), "black")
        result = client.read_pair([image, image], [image, image])
        self.assertEqual(result, (150, 110))
        self.assertEqual(client.used, 1)
        with self.assertRaises(GeminiLimitError):
            client.read_pair([image, image], [image, image])
        self.assertEqual(len(requests), 1)

    def test_erro_429_suspende_chamadas_posteriores(self):
        attempts = []
        def forbidden(request, timeout):
            attempts.append(1)
            raise urllib.error.HTTPError("https://example.test/", 429,
                                         "Too Many Requests", None, None)
        client = GeminiClient("EXAMPLE_NOT_REAL_KEY", max_requests=5,
                              transport=forbidden)
        image = Image.new("RGB", (48, 24), "black")
        with self.assertRaises(GeminiLimitError):
            client.read_pair([image, image], [image, image])
        with self.assertRaises(GeminiLimitError):
            client.read_pair([image, image], [image, image])
        self.assertEqual(len(attempts), 1)

    def test_chave_nao_e_salva_em_texto_puro(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "CortadorPLO" / "chave.dpapi"
            def fake_dpapi(value, decrypt=False):
                return value[3:][::-1] if decrypt else b"DP1" + value[::-1]
            with patch("gemini_backend.key_file_path", return_value=path), \
                 patch("gemini_backend._protect_bytes", side_effect=fake_dpapi), \
                 patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
                save_key("EXAMPLE_NOT_REAL_KEY")
                self.assertNotIn(b"EXAMPLE_NOT_REAL_KEY", path.read_bytes())
                self.assertEqual(read_key(), "EXAMPLE_NOT_REAL_KEY")

    def test_ia_so_acionada_se_ocr_nao_confirma(self):
        frame = Image.new("L", (35, 20), 15)
        state = HandState()
        state.pending = {"start": 6, "end": 35,
                         "before": [frame, frame], "after": [frame, frame]}
        fallback = Mock(return_value=(150, 110))
        with patch("analise_video.stack_median",
                   side_effect=[(None, 0), (None, 0)]):
            state.finish(1, 1, 30, "tesseract", quick=False,
                         gemini_reader=fallback)
        fallback.assert_called_once()
        self.assertEqual(state.results[0].source, "Gemini")
        self.assertEqual(state.results[0].loss_bb, 40)
        self.assertTrue(state.results[0].auto_verified)

        state = HandState()
        state.pending = {"start": 6, "end": 35,
                         "before": [frame, frame], "after": [frame, frame]}
        fallback = Mock(return_value=(150, 110))
        with patch("analise_video.stack_median",
                   side_effect=[(200, 2), (180, 2)]):
            state.finish(1, 1, 30, "tesseract", quick=False,
                         gemini_reader=fallback)
        fallback.assert_not_called()
        self.assertEqual(state.results, [])


if __name__ == "__main__":
    unittest.main()
