# -*- coding: utf-8 -*-
"""Testes isolados da classificacao final, sem extrair video real.

Rodar: python -m unittest -v testes_fase_final
"""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from analise_video import Candidate, confirm_candidates_by_pot_offline


class ClassificacaoFinalTests(unittest.TestCase):
    def make_candidate(self, low=True):
        during = ([[12, 90], [16, 60], [17, 59]] if low else
                  [[12, 98], [16, 95], [17, 94]])
        return Candidate(
            start=5, end=39.85, table=1, loss_bb=None,
            stack_before=None, stack_after=None,
            status="PENDENTE", layout="horizontal1",
            hand_start=10, hand_end=20,
            next_deal_at=40, segment_end=50,
            hero_invested_bb=None,
            stack_before_trace=[[8, 100], [9, 100]],
            stack_trace=during,
        )

    def classify(self, candidate, fold_score):
        config = {"1": {"bb": "1"}}
        video = SimpleNamespace(duration=50)
        with patch("analise_video.resource", return_value="dummy"), \
             patch("analise_video.native_stack_crop", return_value=object()), \
             patch("analise_video.read_fold_score", return_value=fold_score), \
             patch("analise_video.ocr_stack", return_value=95):
            result, evaluated, confirmed = confirm_candidates_by_pot_offline(
                [video], config, [candidate], 30)
        return result[0], evaluated, confirmed

    def test_fold_e_detectado_sem_aporte_na_primeira_triagem(self):
        hand = self.make_candidate(low=True)
        actual, checked, confirmed = self.classify(hand, fold_score=90)
        self.assertEqual((checked, confirmed), (1, 1))
        self.assertTrue(actual.fold_seen)
        self.assertTrue(actual.fold_confirmed)
        self.assertTrue(actual.auto_verified)
        self.assertGreaterEqual(actual.loss_bb, 30)
        self.assertEqual(actual.end, 39.85)  # permanece ate proxima mao

    def test_fold_de_poucos_bb_nao_e_exportado_automaticamente(self):
        hand = self.make_candidate(low=False)
        actual, checked, confirmed = self.classify(hand, fold_score=90)
        self.assertEqual((checked, confirmed), (1, 0))
        self.assertTrue(actual.fold_seen)
        self.assertFalse(actual.fold_confirmed)
        self.assertIsNone(actual.loss_bb)

    def test_sem_prova_visual_uma_queda_no_saldo_nao_prova_perda(self):
        hand = self.make_candidate(low=True)
        actual, checked, confirmed = self.classify(hand, fold_score=-1)
        self.assertEqual((checked, confirmed), (0, 0))
        self.assertFalse(actual.fold_seen)
        self.assertIsNone(actual.loss_bb)


if __name__ == "__main__":
    unittest.main()
