# -*- coding: utf-8 -*-
"""Testes 100% offline do fluxo aporte -> pote -> adversario -> MP4."""
import unittest
from unittest.mock import patch
from PIL import Image

from desfecho_local import (
    parse_table_lines, evaluate_pot_transfer, _match_seat)
from cortador import Video
from analise_video import (
    Candidate, confirm_candidates_by_pot_offline, screenshot_profile,
    eligible_losses)


def snapshot(pot=None, opponent=140, hero=100, side_pot=False):
    return {
        "pots": [] if pot is None else [pot],
        "seats": [(0.16, 0.37, opponent), (0.52, 0.91, hero)],
        "side_pot": side_pot,
        "winner_labels": [],
    }


class EndOfHandTests(unittest.TestCase):
    def test_45bb_investido_e_pote_ao_adversario(self):
        before = snapshot(pot=None, opponent=140, hero=100)
        end = snapshot(pot=110, opponent=95, hero=55)
        after1 = snapshot(pot=None, opponent=185, hero=100)
        after2 = snapshot(pot=None, opponent=185, hero=100)
        event = evaluate_pot_transfer(before, end, after1, after2, 45, 30)
        self.assertTrue(event["confirmed"])
        self.assertEqual(event["loss_bb"], 45)
        self.assertIn("adversario", event["winner"])

    def test_stack_de_200bb_nao_e_assumido_como_100bb(self):
        event = evaluate_pot_transfer(
            snapshot(opponent=150, hero=200),
            snapshot(pot=170, opponent=110, hero=140),
            snapshot(opponent=210, hero=200),
            snapshot(opponent=210, hero=200),
            60, 30)
        self.assertTrue(event["confirmed"])
        self.assertEqual(event["loss_bb"], 60)

    def test_aporte_29_bb_nao_atinge_30(self):
        event = evaluate_pot_transfer(
            snapshot(opponent=140), snapshot(pot=90, opponent=110),
            snapshot(opponent=169), snapshot(opponent=169), 29.5, 30)
        self.assertFalse(event["confirmed"])

    def test_pote_nao_desapareceu(self):
        event = evaluate_pot_transfer(
            snapshot(opponent=100), snapshot(pot=80),
            snapshot(pot=80, opponent=145),
            snapshot(pot=60, opponent=145), 45, 30)
        self.assertFalse(event["confirmed"])

    def test_side_pot_nao_e_auto_confirmado(self):
        event = evaluate_pot_transfer(
            snapshot(opponent=100), snapshot(pot=110, side_pot=True),
            snapshot(opponent=150), snapshot(opponent=150), 45, 30)
        self.assertFalse(event["confirmed"])
        self.assertIn("side pot", event["reason"])

    def test_heroi_recebeu_fichas_e_automatico_fica_pendente(self):
        # Mesmo com outro jogador ganhando, se o heroi tambem recebeu
        # fichas o valor liquido nao equivale ao aporte bruto.
        result = evaluate_pot_transfer(
            snapshot(opponent=140, hero=100),
            snapshot(pot=120, opponent=110, hero=65),
            snapshot(opponent=185, hero=118),
            snapshot(opponent=185, hero=118),
            35, 30)
        self.assertFalse(result["confirmed"])
        self.assertIn("Heroi tambem ganhou", result["reason"])

    def test_jogador_sem_stack_pos_nao_e_falso_positivo(self):
        result = evaluate_pot_transfer(
            snapshot(opponent=140), snapshot(pot=110),
            snapshot(opponent=185), {"pots": [], "seats": [], "side_pot": False},
            45, 30)
        self.assertFalse(result["confirmed"])

    def test_oponente_so_aumenta_em_um_quadro_e_inconclusivo(self):
        result = evaluate_pot_transfer(
            snapshot(opponent=140), snapshot(pot=90),
            snapshot(opponent=185), snapshot(opponent=150), 45, 30)
        self.assertFalse(result["confirmed"])

    def test_numeros_no_pote_nao_sao_confundidos_com_stack(self):
        lines = [("POTE 104,5 BB", 120, 200),
                 ("~Pulgar~ 100,0 BB", 135, 478),
                 ("vilao 152,5BB", 35, 160)]
        reading = parse_table_lines(lines, 320, 540)
        self.assertEqual(reading["pots"], [104.5])
        self.assertEqual(len(reading["seats"]), 2)
        self.assertEqual(reading["seats"][0][2], 100)
        self.assertEqual(reading["seats"][1][2], 152.5)

    def test_candidato_com_transferecia_gera_perda_confirmada(self):
        video = Video("video.mp4", 100, 1920, 1080, False)
        c = Candidate(
            5, 45, 1, None, None, None,
            "PRIORIDADE - APORTE >= LIMITE",
            nick="~Pulgar~", layout="horizontal3",
            hand_start=10, hand_end=40, hero_invested_bb=45,
            before_times=[8], after_times=[41, 43])
        snapshots = [
            snapshot(opponent=140),
            snapshot(pot=80, opponent=95),
            snapshot(opponent=185),
            snapshot(opponent=185),
        ]
        with patch("analise_video.resource", return_value="ffmpeg"), \
             patch("analise_video.native_stack_crop",
                   return_value=Image.new("RGB", (180, 160), "green")), \
             patch("analise_video.read_table_ocr", side_effect=snapshots):
            result, evaluated, approved = confirm_candidates_by_pot_offline(
                [video], screenshot_profile(), [c], 30)
        self.assertEqual((evaluated, approved), (1, 1))
        self.assertTrue(result[0].pot_verified)
        self.assertEqual(result[0].loss_bb, 45)
        self.assertEqual(
            eligible_losses(result, 30, automatic_only=True,
                            require_pot_evidence=True), result)


if __name__ == "__main__":
    unittest.main()
