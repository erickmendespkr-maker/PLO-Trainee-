# -*- coding: utf-8 -*-
"""Testes offline do PLO com rebuy automatico: sem rede nem video real."""
import json
import unittest
from unittest.mock import patch

from PIL import Image

from cortador import Video
from poker_contexto import (
    finite_amount, normalize_nick, table_context_timestamps,
    validate_pot_result
)
from analise_video import (
    Candidate, HandState, eligible_losses, screenshot_profile,
    recheck_candidates_with_poker_context
)
from gemini_backend import GeminiClient


def proof(amount=40.0, winner="adversario", rebuy=True):
    return {
        "hero_nick": "~Pulgar~",
        "same_hand": True, "hand_finished": True,
        "hero_invested_bb": amount, "investment_visibly_verified": True,
        "pot_awarded_to_opponent": True, "winner_nick": winner,
        "hero_won_any_pot": False, "auto_rebuy_seen": rebuy,
        "evidence": "Hero colocou fichas e o pote foi entregue ao adversario",
    }


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps({"candidates": [{"content": {
            "parts": [{"text": json.dumps(self.body)}]}}]}).encode("utf-8")


class PokerContextTests(unittest.TestCase):
    def test_rebuy_100_55_100_e_perda_45(self):
        result = validate_pot_result(proof(45, rebuy=True), "~Pulgar~", 30)
        self.assertTrue(result["verified"])
        self.assertEqual(result["loss_bb"], 45)
        self.assertTrue(result["auto_rebuy_seen"])

    def test_stack_150_ou_200_nao_muda_regra_de_perda(self):
        for money in (30, 35, 72):
            result = validate_pot_result(proof(money), "~Pulgar~", 30)
            self.assertTrue(result["verified"])
            self.assertEqual(result["loss_bb"], money)
        self.assertFalse(
            validate_pot_result(proof(29.9), "~Pulgar~", 30)["verified"])

    def test_pote_grande_com_aporte_de_20bb_nao_e_perda_30bb(self):
        reported = proof(20)
        reported["evidence"] = "Pote total 100BB, hero colocou 20BB"
        self.assertFalse(validate_pot_result(reported, "~Pulgar~", 30)["verified"])

    def test_nao_exportar_sem_confirmacao_do_vencedor(self):
        for field, value in [
            ("pot_awarded_to_opponent", None),
            ("hero_won_any_pot", None),
            ("hand_finished", False),
            ("same_hand", False),
            ("winner_nick", None),
            ("investment_visibly_verified", False),
            ("hero_nick", "outro_jogador"),
        ]:
            event = proof()
            event[field] = value
            self.assertFalse(
                validate_pot_result(event, "~Pulgar~", 30)["verified"],
                msg=f"deveria rejeitar {field}={value}")
        side_pot = proof()
        side_pot["hero_won_any_pot"] = True
        self.assertFalse(validate_pot_result(side_pot, "~Pulgar~", 30)["verified"])

    def test_nao_inferir_aporte_do_total_do_pote(self):
        entry = proof(50)
        entry["hero_invested_bb"] = None
        entry["investment_visibly_verified"] = False
        self.assertFalse(validate_pot_result(entry, "~Pulgar~", 30)["verified"])
        self.assertIsNone(finite_amount("50BB"))

    def test_scan_rebuy_registra_mao_sem_consultar_saldo(self):
        frames = [Image.new("L", (170, 112), 45)]
        state = HandState()
        state.layout = state.scan_mode = "horizontal3"
        state.pending = {
            "start": 10, "end": 48,
            "before": frames, "after": frames,
            "before_times": [7, 8], "after_times": [49, 50]
        }
        with patch("analise_video.stack_median") as ocr:
            state.finish(1, 1.0, 30, "fake_ocr", auto_rebuy=True)
        ocr.assert_not_called()
        self.assertEqual(len(state.results), 1)
        c = state.results[0]
        self.assertIsNone(c.loss_bb)
        self.assertFalse(c.auto_verified)
        self.assertEqual((c.hand_start, c.hand_end), (10, 48))

    def test_exportacao_rebuy_exige_pote_ou_confirmacao_manual(self):
        old = Candidate(0, 30, 1, 45, 100, 55, "OCR",
                        auto_verified=True)
        new = Candidate(30, 60, 1, 45, None, None, "POTE",
                        auto_verified=True, pot_verified=True)
        self.assertEqual(eligible_losses([old, new], 30), [old, new])
        self.assertEqual(eligible_losses(
            [old, new], 30, require_pot_evidence=True), [new])
        old.confirmed = True
        self.assertEqual(eligible_losses(
            [old, new], 30, require_pot_evidence=True), [old, new])
        self.assertEqual(eligible_losses(
            [old, new], 30, automatic_only=True,
            require_pot_evidence=True), [new])

    def test_tempos_cobrem_streets_ao_longo_da_mao(self):
        times = table_context_timestamps(10, 50, 90)
        self.assertEqual(len(times), 10)
        self.assertTrue(all(10 <= x <= 50 for x in times[:8]))
        self.assertTrue(all(x > 50 for x in times[8:]))
        times2 = table_context_timestamps(
            10, 50, 90, after_times=[51, 52, 53, 54])
        self.assertEqual(times2[-2:], [51, 53])
        self.assertIsNone(table_context_timestamps(10, 11.5, 90))

    def test_contexto_enviado_para_gemini_tela_e_mesa_inteira(self):
        sent = []
        def fake_transport(request, timeout):
            body = json.loads(request.data.decode("utf-8"))
            sent.append(body)
            return FakeResponse(proof(40))
        client = GeminiClient(
            "EXAMPLE_NOT_REAL_KEY", transport=fake_transport, max_requests=1)
        picture = Image.new("RGB", (160, 100), "green")
        result = client.read_hand_context(
            picture, [picture] * 10, [picture] * 2, "~Pulgar~", 30)
        self.assertTrue(result["verified"])
        parts = sent[0]["contents"][0]["parts"]
        images = [p["inline_data"] for p in parts if "inline_data" in p]
        self.assertEqual(len(images), 13)
        self.assertTrue(all(p["mime_type"] == "image/jpeg" for p in images))
        self.assertEqual(client.used, 1)

    def test_reanalisar_video_rebuy_gera_prova_e_nao_reconsulta(self):
        video = Video("video.mp4", 100, 1920, 1080, True)
        candidate = Candidate(
            5, 55, 1, None, None, None,
            "INCONCLUSIVO - AGUARDANDO POTE/REBUY",
            nick="~Pulgar~", layout="horizontal3",
            hand_start=10, hand_end=50
        )
        class StubGemini:
            disabled_reason = None
            limit = 1
            used = 0
            def read_hand_context(self, overview, table_frames, hud_frames,
                                  expected_nick, threshold):
                self.used += 1
                assert len(table_frames) == 10 and len(hud_frames) == 2
                return validate_pot_result(
                    proof(40), expected_nick, threshold)
        stub = StubGemini()
        with patch("analise_video.resource", return_value="ffmpeg"), \
             patch("analise_video.native_stack_crop",
                   return_value=Image.new("RGB", (150, 120), "green")) as crop:
            revised, checked, approved = recheck_candidates_with_poker_context(
                [video], screenshot_profile(), [candidate], 30, stub)
        self.assertEqual((checked, approved), (1, 1))
        self.assertEqual(crop.call_count, 13)
        self.assertEqual(revised[0].loss_bb, 40)
        self.assertTrue(revised[0].pot_verified)
        self.assertEqual(revised[0].winner_nick, "adversario")
        with patch("analise_video.native_stack_crop") as not_again:
            after, checked, approved = recheck_candidates_with_poker_context(
                [video], screenshot_profile(), revised, 30, stub)
        self.assertEqual((checked, approved), (0, 0))
        not_again.assert_not_called()


if __name__ == "__main__":
    unittest.main()
