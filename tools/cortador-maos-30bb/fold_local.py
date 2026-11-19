# -*- coding: utf-8 -*-
"""Deteccao offline de 'FOLD' sobre o avatar do heroi, sem IA ou internet.

Texto em qualquer outro assento NAO prova o fold do heroi.
A ROI e obtida da marcacao do HUD do heroi, com extensao acima do avatar.
"""
from __future__ import annotations

import re
import subprocess
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
    box = (max(left, int(x1)),
           max(top, round(y1 - .48 * height)),
           min(right, round(x1 + .53 * width)),
           min(bottom, round(y1 + .62 * height)))
    return box if box[2] - box[0] >= 12 and box[3] - box[1] >= 12 else None


def read_fold_score(image, tesseract):
    """Confere a palavra exata FOLD usando OCR TSV e confianca da leitura."""
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
    return max_score


def fold_overlay_confirmed(scores):
    """Um quadro muito claro ou dois tempos distintos com OCR coerente."""
    valid = [float(s) for s in scores if s is not None and s >= 0]
    return any(s >= 78 for s in valid) or sum(s >= 48 for s in valid) >= 2
