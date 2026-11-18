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


BALANCE_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])(\d{1,5}(?:[.,]\s*\d{1,3})?)"
    r"\s*(?:B\s*B|8\s*B|B\s*8)(?![A-Za-z0-9])",
    flags=re.IGNORECASE,
)


def _balance_observation(raw, parse_amount):
    """(saldo, decimal_explicito) ou None se o mesmo recorte tem valores distintos."""
    if not raw:
        return None
    candidates = []
    for match in BALANCE_PATTERN.finditer(raw):
        literal = match.group(1)
        value = parse_amount(literal)
        if value is not None:
            candidates.append((value, "." in literal or "," in literal))
    if not candidates:
        return None
    first = candidates[0][0]
    if any(abs(value - first) > .025 for value, _decimal in candidates):
        return None
    return (first, any(decimal for _value, decimal in candidates))


def hud_balance_from_text(raw, parse_amount):
    """Extrai saldo com BB; preserva informação de vírgula no caminho detalhado."""
    candidate = _balance_observation(raw, parse_amount)
    return candidate[0] if candidate else None


def _consistent_hud_balance(observations):
    """Concilia leituras, sem inferir 100 BB como valor inicial.

    Exemplo observado: um filtro lê 990BB e outro 99.0 BB.
    Só corrigir o primeiro com evidência EXPLÍCITA de decimal no segundo.
    Nunca dividir valores inteiros por 10 por mera suposição.
    """
    if not observations:
        return None
    decimals = [value for value, explicit in observations if explicit]
    if decimals:
        pivot = sorted(decimals)[len(decimals) // 2]
        tolerance = max(.06, abs(pivot) * .003)
        if any(abs(v - pivot) > tolerance for v in decimals):
            return None
        for value, explicit in observations:
            if abs(value - pivot) <= tolerance:
                continue
            # "990 BB" e "99.0 BB" têm os mesmos dígitos: o OCR apagou
            # somente o separador decimal em UM recorte da mesma imagem.
            if (not explicit and
                    abs(value - pivot * 10) <= .06 and
                    abs(pivot * 10 - round(pivot * 10)) <= .06):
                continue
            if (not explicit and
                    abs(value - pivot * 100) <= .06 and
                    abs(pivot * 100 - round(pivot * 100)) <= .06):
                continue
            return None
        return round(pivot, 3)
    # Se nenhum filtro enxergou vírgula ou ponto, exigir duas regiões
    # concordantes antes de devolver um inteiro. Caso contrário, Gemini.
    if len(observations) < 2:
        return None
    first = observations[0][0]
    if all(abs(value - first) <= max(.1, first * .002)
           for value, _explicit in observations):
        return first
    return None


def read_hud_stack(image, executable, parse_amount, quick=False):
    """OCR do HUD completo. Regiões variam; nenhum retângulo antigo é usado."""
    regions = hud_search_regions(image)
    by_name = {name: patch for name, patch in regions}
    # O centro inferior foi a única região que capturou "99.0 BB"
    # corretamente no vídeo real; o esquerdo inferior leu "990BB".
    # Consultá-lo primeiro elimina um falso positivo em modo rápido.
    jobs = [
        ("hud_centro_inferior", 11),
        ("hud_esquerdo_inferior", 6),
        ("hud_inteiro", 11),
    ]
    if not quick:
        jobs += [("hud_linha_saldo", 7)]
    results = []
    observations = []
    with tempfile.TemporaryDirectory(prefix="plo_hud_stack_") as folder:
        for index, (name, psm) in enumerate(jobs):
            raw = _ocr(by_name[name], executable, psm,
                       Path(folder) / f"{index}.png")
            candidate = _balance_observation(raw, parse_amount)
            amount = candidate[0] if candidate else None
            results.append((name, psm, raw, amount))
            if candidate:
                observations.append(candidate)
                # Em modo rápido: decimal legível, sem outra região em
                # conflito ainda. O uso para corte exige OUTROS FRAMES.
                if quick and candidate[1]:
                    return amount, results
        return _consistent_hud_balance(observations), results


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
