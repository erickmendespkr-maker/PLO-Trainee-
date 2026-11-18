# -*- coding: utf-8 -*-
"""Testes do motor OFFLINE: nenhum cliente HTTP, API ou servico externo."""
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
from cortador import Video
from analise_local import (
    assess_stacks, offline_review_decision, times_for_hand)
from analise_video import (
    Candidate, eligible_losses, estimate_candidates_offline, screenshot_profile)


class OfflinePokerTests(unittest.TestCase):
    def test_rebuy_automatico_nao_zera_aporte_estimado(self):
        result = assess_stacks(
            before=[100.0], during=[95, 65, 55, 55, 60, 65, 75],
            after=[100.0], bb=1, threshold=30)
        self.assertTrue(result["prioritize"])
        self.assertEqual(result["invested_estimate_bb"], 45.0)
        self.assertTrue(result["rebuy_possible"])

    def test_150_200bb_de_stack_nao_se_reduz_a_100bb(self):
        for baseline, floor, expected in ((150, 110, 40), (200, 140, 60)):
            result = assess_stacks(
                [baseline], [baseline, floor, floor, floor],
                [baseline], bb=1, threshold=30)
            self.assertEqual(result["invested_estimate_bb"], expected)
            self.assertTrue(result["prioritize"])

    def test_100bb_de_pote_nao_prova_investimento_do_heroi(self):
        result = assess_stacks(
            [100], [100, 90, 80, 80], [100], bb=1, threshold=30)
        self.assertFalse(result["prioritize"])
        self.assertEqual(result["invested_estimate_bb"], 20)

    def test_zero_isolado_de_ocr_nao_gera_falsa_perda(self):
        result = assess_stacks(
            [150], [150, 145, 0, 142, 143], [150], bb=1, threshold=30)
        self.assertFalse(result["prioritize"])
        self.assertEqual(result["invested_estimate_bb"], 8)

    def test_stack_intra_mao_nao_confirma_vencedor_automaticamente(self):
        candidate = Candidate(
            5, 45, 1, None, None, None,
            "PENDENTE", hero_invested_bb=45, auto_verified=False)
        self.assertEqual(
            eligible_losses([candidate], 30, require_pot_evidence=True), [])
        self.assertFalse(offline_review_decision(45, 30, "incerto"))
        self.assertFalse(offline_review_decision(45, 30, "hero_tudo"))
        self.assertTrue(offline_review_decision(45, 30, "oponente_tudo"))
        self.assertTrue(offline_review_decision(
            35, 30, "hero_parte_liquido_conferido"))
        self.assertFalse(offline_review_decision(
            29.9, 30, "hero_parte_liquido_conferido"))
        candidate.confirmed = True
        candidate.loss_bb = 45
        self.assertEqual(
            eligible_losses([candidate], 30, require_pot_evidence=True),
            [candidate])

    def test_ja_comecou_a_mao_na_gravacao_sem_frame_previo(self):
        c = Candidate(
            0, 35, 1, None, None, None, "pendente",
            hand_start=0, hand_end=30)
        self.assertIsNone(times_for_hand(c, 50))

    def test_reutilizar_horarios_salvos_no_json_anterior(self):
        c = Candidate(
            5, 45, 1, None, None, None, "pendente",
            before_times=[6, 7], after_times=[41, 42],
            hand_start=10, hand_end=40)
        times = times_for_hand(c, 100, inside_samples=7)
        self.assertEqual(times["before"], [7])
        self.assertEqual(times["after"], [41])
        self.assertEqual(len(times["during"]), 7)
        self.assertTrue(all(10 < t < 40 for t in times["during"]))

    def test_pipeline_local_prioriza_mas_nao_exporta_perda_sem_veredito(self):
        video = Video("falso.mp4", 100., 1920, 1080, False)
        c = Candidate(
            5, 45, 1, None, None, None,
            "INCONCLUSIVO - AGUARDANDO POTE/REBUY",
            layout="horizontal3", nick="~Pulgar~",
            hand_start=10, hand_end=40, before_times=[8],
            after_times=[41])
        # Antes 100; 7 leituras durante; depois 100 por rebuy.
        sequence = [100, 100, 95, 65, 55, 55, 60, 65, 100]
        with patch("analise_video.resource", return_value="ffmpeg"), \
             patch("analise_video.native_stack_crop",
                   return_value=Image.new("RGB", (200, 140), "green")) as frames, \
             patch("analise_video.ocr_stack",
                   side_effect=sequence) as ocr:
            candidates, analyzed, priorities = estimate_candidates_offline(
                [video], screenshot_profile(), [c], 30)
        self.assertEqual((analyzed, priorities), (1, 1))
        self.assertEqual(frames.call_count, 9)
        self.assertEqual(ocr.call_count, 9)
        self.assertEqual(candidates[0].hero_invested_bb, 45.0)
        self.assertIsNone(candidates[0].loss_bb)
        self.assertFalse(candidates[0].pot_verified)
        self.assertFalse(candidates[0].auto_verified)
        self.assertIn("PRIORIDADE", candidates[0].status)


if __name__ == "__main__":
    unittest.main()
