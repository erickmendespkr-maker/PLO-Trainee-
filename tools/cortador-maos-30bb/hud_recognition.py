# -*- coding: utf-8 -*-
"""Leitura visual de um HUD INTEIRO: cartas, nick e stack em uma unica caixa.

A busca por texto percorre o HUD completo e varias faixas candidatas.
Nenhum recorte estreito de "nick" ou "saldo" e exigido do usuario.
"""
from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageEnhance, ImageOps


def is_full_hud(image):
    """Diferencia HUD grande de um recorte legado contendo so um numero."""
    return image.width >= 65 and image.height >= 45


def hud_search_regions(image):
    """Areas de pesquisa DENTRO da caixa verde, sem coordenadas fixas no video."""
    width, height = image.size
    return [
        ("hud_inteiro", image),
        ("hud_esquerdo_inferior",
         image.crop((0, round(height * .30), round(width * .72), height))),
        ("hud_centro_inferior",
         image.crop((round(width * .10), round(height * .44),
                     round(width * .75), round(height * .90)))),
        ("hud_linha_saldo",
         image.crop((round(width * .08), round(height * .58),
                     round(width * .72), round(height * .88)))),
    ]


def _ocr(image, executable, psm, path):
    image = image.convert("L")
    # A imagem nativa chega em alta resolucao, nao redimensionar para baixo.
    factor = max(2, min(5, round(720 / max(image.width, 1))))
    scaled = ImageOps.autocontrast(image.resize(
        (image.width * factor, image.height * factor), Image.Resampling.LANCZOS))
    scaled = ImageOps.expand(scaled, border=16, fill=235)
    scaled.save(path)
    cmd = [executable, str(path), "stdout", "--psm", str(psm)]
    try:
        process = subprocess.run(
            cmd, capture_output=True, text=True, errors="replace", timeout=18,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return process.stdout.strip() if process.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def hud_balance_from_text(raw, parse_amount):
    """Escolhe somente o saldo que acompanha BB; nao confunde cartas/pote."""
    if not raw:
        return None
    numbers = []
    # BB tambem pode ser confundido com 8B pelo OCR.
    expression = (
        r"(?<![A-Za-z0-9])"
        r"(\d{1,5}(?:[.,]\s*\d{1,3})?)"
        r"\s*(?:B\s*B|8\s*B|B\s*8)(?![A-Za-z0-9])"
    )
    for match in re.finditer(expression, raw, flags=re.IGNORECASE):
        amount = parse_amount(match.group(1))
        if amount is not None:
            numbers.append(amount)
    unique = []
    for amount in numbers:
        if not any(abs(amount - x) < .02 for x in unique):
            unique.append(amount)
    return unique[0] if len(unique) == 1 else None


def read_hud_stack(image, executable, parse_amount, quick=False):
    """Retorna (saldo, diagnosticos), sempre analisando a caixa verde grande."""
    regions = hud_search_regions(image)
    jobs = [
        (regions[0], 11),
        (regions[1], 6),
    ]
    if not quick:
        jobs += [(regions[2], 11), (regions[3], 7)]
    results = []
    values = []
    with tempfile.TemporaryDirectory(prefix="plo_hud_stack_") as folder:
        for index, ((name, patch), psm) in enumerate(jobs):
            text = _ocr(patch, executable, psm, Path(folder) / f"{index}.png")
            amount = hud_balance_from_text(text, parse_amount)
            # Na linha inferior, um unico numero sem BB pode ser aceito
            # apenas se a faixa for especificamente a ultima linha do HUD.
            if amount is None and name == "hud_linha_saldo":
                only_number = text.replace(" ", "").strip()
                if re.fullmatch(r"\d{1,5}(?:[.,]\d{1,3})?", only_number):
                    amount = parse_amount(only_number)
            results.append((name, psm, text, amount))
            if amount is not None:
                values.append(amount)
                if quick:
                    return amount, results
    if not values:
        return None, results
    # A concordancia de dois QUADROS diferentes continua sendo obrigatoria
    # antes de exportar uma perda; consenso entre variantes nao a substitui.
    for value in values:
        if sum(abs(other-value) <= max(.7, value*.008) for other in values) >= 2:
            return value, results
    return values[0] if len(values) == 1 else None, results


def read_hud_nick(image, executable):
    """Extrai linhas candidatas do HUD inteiro e da parte esquerda inferior."""
    regions = hud_search_regions(image)
    jobs = [(regions[0], 11), (regions[1], 6), (regions[2], 11)]
    readings = []
    with tempfile.TemporaryDirectory(prefix="plo_hud_nick_") as folder:
        for index, ((name, patch), psm) in enumerate(jobs):
            value = _ocr(patch, executable, psm, Path(folder) / f"{index}.png")
            if value:
                for line in value.splitlines():
                    line = line.strip()
                    if line and line not in readings:
                        readings.append(line)
    return readings
