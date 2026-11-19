# -*- coding: utf-8 -*-
"""Testes offline da fusao visual e do detector de Fold do avatar."""
import base64
import unittest
import zlib

from PIL import Image

from fold_local import (
    _BANNER_B85, _BANNER_SIZE, fold_template_score,
    fold_overlay_confirmed, fold_overlay_roi,
)


class FusaoVisualTest(unittest.TestCase):
    def test_template_usuario_e_valido(self):
        data = zlib.decompress(base64.b85decode(_BANNER_B85))
        self.assertEqual(len(data), _BANNER_SIZE[0] * _BANNER_SIZE[1])

    def test_fold_acima_do_avatar_na_roi(self):
        # Screenshot ilustrativo 280x189: HUD comecando em x80,y111.
        area = fold_overlay_roi((80, 111, 232, 163), (0, 0, 280, 189))
        self.assertLessEqual(area[0], 68)
        self.assertLessEqual(area[1], 79)
        self.assertGreaterEqual(area[2], 111)
        self.assertGreaterEqual(area[3], 94)

    def test_template_visual_positive_se_cv2_instalado(self):
        try:
            import cv2  # noqa
        except ImportError:
            self.skipTest("OpenCV nao instalado, OCR Tesseract continua ativo")
        data = zlib.decompress(base64.b85decode(_BANNER_B85))
        template = Image.frombytes("L", _BANNER_SIZE, data)
        crop = Image.new("L", (220, 96), 40)
        crop.paste(template, (45, 30))
        self.assertGreaterEqual(fold_template_score(crop), 90)

    def test_nao_confirma_so_com_ocr_fraco(self):
        self.assertFalse(fold_overlay_confirmed([-1, 0, 65]))
        self.assertTrue(fold_overlay_confirmed([90]))
        self.assertTrue(fold_overlay_confirmed([81, 83]))


if __name__ == "__main__":
    unittest.main()
