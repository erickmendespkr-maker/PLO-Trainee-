# -*- coding: utf-8 -*-
import unittest
from rastreador_eventos import perda_por_fold, eventos_de_stack


class TesteRastreadorEventos(unittest.TestCase):
    def test_fold_com_aporte_42bb(self):
        r = perda_por_fold([(1, 100), (2, 100)],
            [(5, 100), (6, 100), (8, 82), (9, 82), (12, 58), (13, 58)],
            1, 30, 14)
        self.assertTrue(r.confirmado, r.motivo)
        self.assertEqual(r.perda_bb, 42)

    def test_fold_20bb_nao_exporta(self):
        r = perda_por_fold([(1, 100), (2, 100)],
            [(5, 100), (6, 100), (7, 80), (8, 80)], 1, 30, 9)
        self.assertFalse(r.confirmado)
        self.assertEqual(r.investimento_bb, 20)

    def test_rebuy_100_bb_sem_perda_automatica(self):
        r = perda_por_fold([(1, 100), (2, 100)],
            [(5, 100), (6, 100), (7, 45), (8, 45), (9, 100), (10, 100)],
            1, 30, 11)
        self.assertFalse(r.confirmado)
        self.assertTrue(r.rebuy_possivel)

    def test_valor_isolado_ocr_nao_e_aposta(self):
        r = perda_por_fold([(1, 100), (2, 100)],
            [(5, 100), (6, 100), (7, 2), (8, 100), (9, 100)],
            1, 30, 10)
        self.assertFalse(r.confirmado)

    def test_leituras_iniciais_incoerentes(self):
        r = perda_por_fold([(1, 100), (2, 160)],
            [(5, 100), (6, 100), (7, 60), (8, 60)], 1, 30, 9)
        self.assertFalse(r.confirmado)

    def test_patamar_de_stack_dois_quadros(self):
        states, actions = eventos_de_stack(
            [(1, 100), (2, 100), (3, 58), (4, 58)], 1)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].tipo, "saida")

    def test_valores_bb_em_reais(self):
        r = perda_por_fold([(1, 200), (2, 200)],
            [(5, 200), (6, 200), (7, 116), (8, 116)], 2, 30, 9)
        self.assertTrue(r.confirmado)
        self.assertEqual(r.perda_bb, 42)


if __name__ == "__main__":
    unittest.main()
