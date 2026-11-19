# -*- coding: utf-8 -*-
"""Testes locais sem video, Gemini, internet nem API.

Executar dentro de tools/cortador-maos-30bb:
    python -m unittest -v testes_fluxo_offline
"""
import unittest
from types import SimpleNamespace

from analise_local import times_for_hand, assess_stacks, offline_review_decision
from desfecho_local import parse_table_lines, evaluate_pot_transfer
from limites_maos import estender_ate_proxima_distribuicao
from fold_local import has_fold_label, fold_overlay_roi, fold_overlay_confirmed
from analise_local import confirmed_fold_investment


class TesteTriagemOffline(unittest.TestCase):
    def test_amostras_nao_invadem_proxima_mao(self):
        hand = SimpleNamespace(
            start=5, end=35, hand_start=10, hand_end=30,
            before_times=[8, 9], after_times=[32, 33])
        t = times_for_hand(hand, 100, inside_samples=15)
        self.assertEqual(t["before"], [8, 9])
        self.assertEqual(t["after"], [32])
        self.assertEqual(len(t["during"]), 15)
        self.assertTrue(all(10 < x < 30 for x in t["during"]))

    def test_rebuy_nao_prova_perda(self):
        estimate = assess_stacks(
            before=[100], during=[95, 85, 55, 41, 42],
            after=[100], bb=1, threshold=30)
        self.assertTrue(estimate["prioritize"])
        self.assertEqual(estimate["invested_estimate_bb"], 59)
        self.assertTrue(estimate["rebuy_possible"])
        self.assertFalse(offline_review_decision(
            estimate["invested_estimate_bb"], 30, "incerto"))


class TesteLimitesEFold(unittest.TestCase):
    def _hand(self, table, start, vanish, segment_end=200):
        return SimpleNamespace(
            table=table, layout="horizontal4",
            start=max(0, start - 5), end=vanish + 5,
            hand_start=start, hand_end=vanish,
            next_deal_at=None, segment_end=segment_end)

    def test_fold_nao_termina_o_mp4(self):
        primeira = self._hand(1, 10, 20)
        segunda = self._hand(1, 70, 80)
        estender_ate_proxima_distribuicao([primeira, segunda], 200)
        self.assertAlmostEqual(primeira.end, 69.85)
        self.assertEqual(primeira.hand_end, 20)
        self.assertEqual(primeira.next_deal_at, 70)

    def test_proxima_mao_de_outra_mesa_nao_encerra_o_corte(self):
        primeira = self._hand(1, 10, 20)
        outra_mesa = self._hand(2, 25, 36)
        segunda = self._hand(1, 70, 75)
        estender_ate_proxima_distribuicao(
            [primeira, outra_mesa, segunda], 200)
        self.assertAlmostEqual(primeira.end, 69.85)

    def test_ultima_mao_acompanha_ate_fim_do_video(self):
        primeira = self._hand(1, 10, 25)
        estender_ate_proxima_distribuicao([primeira], 145)
        self.assertEqual(primeira.end, 145)
        self.assertIsNone(primeira.next_deal_at)

    def test_fold_escrito_no_avatar(self):
        self.assertTrue(has_fold_label("FOLD"))
        self.assertTrue(has_fold_label("Fold"))
        self.assertFalse(has_fold_label("FOLDER"))
        self.assertFalse(has_fold_label("adversario venceu"))

    def test_crop_inclui_texto_acima_da_foto(self):
        roi = fold_overlay_roi((120, 405, 240, 528), (0, 0, 320, 540))
        self.assertLess(roi[1], 405)
        self.assertLessEqual(roi[2], 240)
        self.assertGreater(roi[3], 405)

    def test_fold_em_um_frame_forte_ou_dois_medios(self):
        self.assertTrue(fold_overlay_confirmed([-1, 83]))
        self.assertTrue(fold_overlay_confirmed([60, -1, 55]))
        self.assertFalse(fold_overlay_confirmed([60, -1, 20]))

    def test_aporte_confirmado_por_duas_leituras_e_fold(self):
        valor = confirmed_fold_investment(
            before=[100], during=[95, 62, 61, 60, 60.5],
            bb=1, threshold=30)
        self.assertIsNotNone(valor)
        self.assertGreaterEqual(valor, 30)
        self.assertTrue(offline_review_decision(valor, 30, "hero_fold"))

    def test_nao_confirmar_aporte_por_um_unico_ocr_errado(self):
        valor = confirmed_fold_investment(
            before=[100], during=[99, 97, 20, 96],
            bb=1, threshold=30)
        self.assertIsNone(valor)


class TesteDestinoPote(unittest.TestCase):
    def test_pote_com_legenda_separada_do_numero(self):
        frame = parse_table_lines([
            ("POT", 400, 240),
            ("150,00", 410, 270),
            ("100 BB", 100, 115),
            ("40 BB", 400, 500),
        ], width=800, height=600)
        self.assertIn(150, frame["pots"])
        self.assertEqual(len(frame["seats"]), 2)

    def test_pote_no_centro_sem_legenda(self):
        frame = parse_table_lines([
            ("140 BB", 400, 280),
            ("100 BB", 100, 120),
        ], width=800, height=600)
        self.assertEqual(frame["pots"], [140])
        self.assertEqual(len(frame["seats"]), 1)

    def test_pote_para_adversario_em_duas_leituras(self):
        before = {"seats": [(.15, .20, 100), (.50, .83, 100)],
                  "pots": [], "side_pot": False}
        middle = {"seats": [], "pots": [130], "side_pot": False}
        after1 = {"seats": [(.15, .20, 165), (.50, .83, 40)],
                  "pots": [], "side_pot": False}
        after2 = {"seats": [(.15, .20, 165), (.50, .83, 40)],
                  "pots": [], "side_pot": False}
        result = evaluate_pot_transfer(
            before, middle, after1, after2, invested_bb=60, threshold=30)
        self.assertTrue(result["confirmed"], result["reason"])
        self.assertEqual(result["loss_bb"], 60)

    def test_split_ou_premiacao_heroi_nao_confirma(self):
        before = {"seats": [(.15, .20, 100), (.50, .83, 100)],
                  "pots": [], "side_pot": False}
        middle = {"seats": [], "pots": [150], "side_pot": False}
        after = {"seats": [(.15, .20, 165), (.50, .83, 120)],
                 "pots": [], "side_pot": False}
        result = evaluate_pot_transfer(
            before, middle, after, after, invested_bb=60, threshold=30)
        self.assertFalse(result["confirmed"])

    def test_side_pot_nao_confirma(self):
        before = {"seats": [(.15, .20, 100), (.50, .83, 100)],
                  "pots": [], "side_pot": False}
        middle = {"seats": [], "pots": [160], "side_pot": True}
        after = {"seats": [(.15, .20, 175), (.50, .83, 25)],
                 "pots": [], "side_pot": False}
        result = evaluate_pot_transfer(
            before, middle, after, after, invested_bb=75, threshold=30)
        self.assertFalse(result["confirmed"])
        self.assertIn("side pot", result["reason"].lower())


if __name__ == "__main__":
    unittest.main()
