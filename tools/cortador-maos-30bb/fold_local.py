# -*- coding: utf-8 -*-
"""Deteccao offline de 'FOLD' sobre o avatar do heroi, sem IA ou internet.

Texto em qualquer outro assento NAO prova o fold do heroi.
A ROI e obtida da marcacao do HUD do heroi, com extensao acima do avatar.
"""
from __future__ import annotations

import base64
import re
import subprocess
import zlib
import tempfile
from pathlib import Path

from PIL import Image, ImageOps


_FOLD_WORD = re.compile(r"(?<![A-Z0-9])F[O0]LD(?![A-Z0-9])")


def has_fold_label(text):
    """Evita confundir FOLD com FOLDER e nomes de jogadores."""
    return bool(_FOLD_WORD.search(str(text).upper()))


def fold_overlay_roi(hero_hud, table_box):
    """Retangulo 960x540 centrado na foto do heroi, incluindo area acima."""
    x1, y1, x2, y2 = hero_hud
    left, top, right, bottom = table_box
    width, height = x2 - x1, y2 - y1
    if width < 30 or height < 30:
        return None
    # O aviso Fold fica acima/esquerda do avatar, fora da ROI antiga.
    box = (max(left, round(x1 - .27 * width)),
           max(top, round(y1 - .95 * height)),
           min(right, round(x1 + .65 * width)),
           min(bottom, round(y1 + .61 * height)))
    return box if box[2] - box[0] >= 12 and box[3] - box[1] >= 12 else None


_BANNER_SIZE = (43, 15)
# Referencia visual do aviso Fold fornecida pelo usuario.
_BANNER_B85 = "c$`hr*>0mS7zN<F=}p?S(o~vC>10X@HkcI0;0*^z9Bi|+egDT9XCdh)gslG@7J=*Db^V23xM3WIe(3x0t2?gFbI%T<J~gIp=WF9QxNfkcKXv1^>Uz2DopH|k!`cH)3C^AEK5fQb-(%wZb?1A#u2RmnzGbX2=0Ff-%(Q-luyY!v#vZkv)}?B7YuYotiT2uv@Ga3FSfTd>Yki4Yr@7RPp41<!C}x0EE0*FkY2s|ZpE9%OwBFWDQ=jZmMDsFW6+lUrCN)TRyZT~RvAj~-iON9TlmLm<CQcC)VcIlPR&N;=N?s+2P~`>&P(n!HGREpg5W>X~pNO&)q7YIlKV-K+$gH3R{fXr{<B~C!bIyvNHiiG_SH6(rTogH{jB--klDt?`NfHoxkq01z0Fi8VcQ^Yre@#KK{1+FS_3!6DFN;WN#fg6$JH3xrIz7L?pFPZ9Vo6C7E&_~Smv6!Qx*1G+@c-0UzX_c4TjcBe@!|35={ew?Z6twz7buBAxTc5y9&C<v\""


def fold_template_score(image):
    """Compara o banner real em varias escalas; opcional sem OpenCV."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return -1.
    src = np.asarray(image.convert("L"))
    if src.shape[0] < 16 or src.shape[1] < 35:
        return -1.
    template = np.frombuffer(zlib.decompress(
        base64.b85decode(_BANNER_B85)), dtype=np.uint8).reshape(
            _BANNER_SIZE[1], _BANNER_SIZE[0])
    best = -1.
    for scale in (.70, .85, 1., 1.15, 1.4, 1.7, 2., 2.4, 2.8, 3.2):
        tw = round(template.shape[1] * scale)
        th = round(template.shape[0] * scale)
        if tw > src.shape[1] or th > src.shape[0]:
            continue
        variant = cv2.resize(template, (tw, th),
            interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_CUBIC)
        if variant.std() < 8:
            continue
        scores = cv2.matchTemplate(src, variant, cv2.TM_CCOEFF_NORMED)
        best = max(best, float(np.max(scores)))
    return max(0., min(100., best * 100)) if best >= 0 else -1.


def read_fold_score(image, tesseract):
    """Confere a palavra exata FOLD usando OCR TSV e confianca da leitura."""
    # Evitar depender apenas do OCR quando o banner e muito pequeno.
    template_conf = fold_template_score(image)
    if template_conf >= 90:
        return template_conf
    # Em gravacoes longas, economizar milhares de execucoes do OCR:
    # um quadro visualmente muito diferente nao tem o banner conhecido.
    # Sem OpenCV (valor -1), manter OCR tradicional sem bloqueios.
    if 0 <= template_conf < 48:
        return template_conf
    gray = image.convert("L")
    scale = min(5, max(2, round(620 / max(1, gray.width))))
    enlarged = ImageOps.autocontrast(gray.resize(
        (gray.width * scale, gray.height * scale), Image.Resampling.LANCZOS))
    candidates = [enlarged, ImageOps.invert(enlarged)]
    max_score = -1.
    with tempfile.TemporaryDirectory(prefix="plo_fold_") as temp:
        for i, prepared in enumerate(candidates):
            filename = Path(temp) / f"fold_{i}.png"
            prepared.save(filename)
            cmd = [tesseract, str(filename), "stdout", "--psm", "11", "tsv"]
            try:
                proc = subprocess.run(
                    cmd, capture_output=True, text=True,
                    errors="replace", timeout=18,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            except (subprocess.SubprocessError, OSError):
                continue
            if proc.returncode != 0:
                continue
            for line in proc.stdout.splitlines()[1:]:
                cells = line.split("\t", 11)
                if len(cells) < 12:
                    continue
                try:
                    confidence = float(cells[10])
                except ValueError:
                    continue
                if has_fold_label(cells[11]):
                    max_score = max(max_score, confidence)
            if max_score >= 80:
                break
    return max(max_score, template_conf)


def fold_overlay_confirmed(scores):
    """Um quadro muito claro ou dois tempos distintos com OCR coerente."""
    valid = [float(s) for s in scores if s is not None and s >= 0]
    return any(s >= 90 for s in valid) or sum(s >= 80 for s in valid) >= 2
