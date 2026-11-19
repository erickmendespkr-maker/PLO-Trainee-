# -*- coding: utf-8 -*-
"""Reconhece possivel transferencia de pote em uma MESA INTEIRA, offline.

Usa OCR de saldos posicionados na mesa, e nao apenas o HUD do heroi.
Retorna confirmacao SOMENTE quando ha transferencia consistente, pote
desaparecendo e ausencia de indicio de side pot. Caso contrario: pendente.

Sem API, modelos online ou conexao a internet.
"""
from __future__ import annotations

import math
import re
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageOps

AMOUNT = re.compile(
    r"(?<![a-z0-9])(\d{1,5}(?:[,.]\d{1,2})?)\s*(?:bb|8b)\b",
    re.IGNORECASE
)
POT_WORDS = re.compile(r"\b(pot|pote|total)\b", re.IGNORECASE)
SIDE_POT_WORDS = re.compile(r"\b(side\s*pot|pote\s*lateral|split\s*pot)\b",
                            re.IGNORECASE)
WINNER_WORDS = re.compile(
    r"\b(winner|venceu|ganhou|wins|won)\b", re.IGNORECASE
)


def _parse_amount(text):
    if not isinstance(text, str):
        return None
    text = text.strip()
    if not re.fullmatch(r"\d{1,5}(?:[,.]\d{1,2})?", text):
        return None
    value = float(text.replace(",", "."))
    return value if math.isfinite(value) and 0 <= value <= 5000 else None


def parse_table_lines(lines, width, height):
    """Le stacks e pote da mesa, inclusive quando o OCR separa a legenda POT.

    So aceita numeros soltos em uma regiao plausivel; nunca confunde o
    numero do relogio, das cartas ou de uma aposta com premio confirmado.
    """
    seats, pots, winner_messages = [], [], []
    side_pot = False
    normalized = []
    for raw, cx, cy in lines:
        entry = (str(raw).strip(), cx / max(1, width), cy / max(1, height))
        normalized.append(entry)
        side_pot |= bool(SIDE_POT_WORDS.search(entry[0]))
        if WINNER_WORDS.search(entry[0]):
            winner_messages.append(entry[0])

    pot_labels = [(x, y) for text, x, y in normalized
                  if POT_WORDS.search(text) and not SIDE_POT_WORDS.search(text)]
    isolated_amount = re.compile(r"^\s*(\d{1,5}(?:[,.]\d{1,2})?)\s*$")
    bare_amount = re.compile(r"(?<![a-z0-9])\d{1,5}(?:[,.]\d{1,2})?(?![a-z0-9])",
                             re.IGNORECASE)

    for text, x, y in normalized:
        if not text:
            continue
        explicit = AMOUNT.findall(text)
        in_table_middle = .20 <= x <= .80 and .25 <= y <= .73
        near_pot_label = in_table_middle and any(
            abs(x - px) <= .22 and abs(y - py) <= .13
            for px, py in pot_labels)
        labelled_pot = bool(POT_WORDS.search(text)) and in_table_middle
        if explicit:
            amounts = explicit
        elif labelled_pot:
            amounts = bare_amount.findall(text)
        elif near_pot_label:
            amount = isolated_amount.fullmatch(text)
            amounts = [amount.group(1)] if amount else []
        elif not in_table_middle:
            # Um stack isolado pode vir sem 'BB' no layout da sala.
            # Exigir separador decimal evita ler blinds, timers e nomes.
            amount = isolated_amount.fullmatch(text)
            amounts = [amount.group(1)] if (
                amount and ("," in text or "." in text)) else []
        else:
            amounts = []
        for raw_amount in amounts:
            amount = _parse_amount(raw_amount)
            if amount is None:
                continue
            # Alguns layouts exibem apenas '180 BB' no centro do feltro;
            # isso pode ser o pote. A confirmacao ainda exige seu sumico
            # e o crescimento estavel de um OUTRO jogador.
            central_pot = bool(explicit) and .29 <= x <= .71 and .32 <= y <= .66
            if labelled_pot or near_pot_label or central_pot:
                pots.append(amount)
            else:
                seats.append((round(x, 3), round(y, 3), amount))
    return {"seats": seats, "pots": pots, "winner_labels": winner_messages,
            "side_pot": side_pot}

def read_table_ocr(frame, tesseract):
    """Tesseract TSV: agrupa palavras pela linha, preservando posicoes."""
    img = frame.convert("RGB")
    scale = min(3, max(1, 720 // max(1, img.width)))
    if scale > 1:
        img = img.resize((img.width * scale, img.height * scale),
                         Image.Resampling.LANCZOS)
    img = ImageOps.autocontrast(img.convert("L"))
    with tempfile.TemporaryDirectory(prefix="plo_tabela_") as tmp:
        path = Path(tmp) / "mesa.png"
        img.save(path)
        command = [tesseract, str(path), "stdout", "--psm", "11", "tsv"]
        try:
            process = subprocess.run(
                command, capture_output=True, text=True, errors="replace",
                timeout=18, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except (subprocess.SubprocessError, OSError) as exc:
            raise RuntimeError("Erro de OCR da mesa") from exc
    if process.returncode != 0:
        raise RuntimeError("Tesseract nao conseguiu ler a mesa")
    grouped = {}
    for row in process.stdout.splitlines()[1:]:
        parts = row.split("\t", 11)
        if len(parts) < 12 or parts[0] != "5":
            continue
        try:
            confidence = float(parts[10])
            x, y, w, h = [int(v) for v in parts[6:10]]
            key = (parts[2], parts[3], parts[4])
        except (ValueError, IndexError):
            continue
        word = parts[11].strip()
        if confidence < 15 or not word:
            continue
        grouped.setdefault(key, []).append((x, y, w, h, word))
    lines = []
    for words in grouped.values():
        words.sort(key=lambda entry: entry[0])
        text = " ".join(word for _x, _y, _w, _h, word in words)
        left = min(row[0] for row in words)
        right = max(row[0] + row[2] for row in words)
        top = min(row[1] for row in words)
        bottom = max(row[1] + row[3] for row in words)
        lines.append((text, (left + right) / 2, (top + bottom) / 2))
    return parse_table_lines(lines, img.width, img.height)


def _match_seat(base, target, max_distance=.12):
    """Mesma posicao aproximada antes/depois; nunca misturar jogadores."""
    matches = []
    for seat in target:
        dx, dy = seat[0] - base[0], seat[1] - base[1]
        dist = (dx * dx + dy * dy) ** .5
        if dist <= max_distance:
            matches.append((dist, seat))
    if len(matches) != 1:
        return None
    return matches[0][1]


def _is_hero_zone(seat):
    """Herói esta embaixo e centralizado, configuracao desta gravacao."""
    return seat[1] >= .70 and .24 <= seat[0] <= .76


def evaluate_pot_transfer(before, near_end, after_a, after_b, invested_bb,
                          threshold=30):
    """So aprova vencedor adversario com duas evidencias independentes:

    1. Stack do adversario aumenta na mesma posicao em dois quadros apos.
    2. Pote central visivel antes, ausente ou reduzido apos premiacao.
    Nao presume stack inicial de 100BB. Sem essas provas, deixa pendente.
    """
    result = {"confirmed": False, "winner": None,
              "loss_bb": None, "reason": "Vencedor nao demonstrado"}
    if not isinstance(invested_bb, (int, float)) or invested_bb < threshold:
        result["reason"] = "Aporte do heroi nao ultrapassou o limite"
        return result
    if any(x is None for x in (before, near_end, after_a, after_b)):
        result["reason"] = "Faltaram quadros da mesa para confirmar a transferencia"
        return result
    if any(x.get("side_pot") for x in (before, near_end, after_a, after_b)):
        result["reason"] = "Ha possivel side pot; perda liquida depende de revisao"
        return result
    pots = near_end.get("pots", [])
    if len(pots) != 1 or pots[0] < invested_bb:
        result["reason"] = "Pote central antes da premiacao nao foi lido"
        return result
    end_pots = after_a.get("pots", []) + after_b.get("pots", [])
    if any(amount > max(3, pots[0] * .1) for amount in end_pots):
        result["reason"] = "Pote ainda na mesa; premiacao nao confirmada"
        return result
    # A transferencia precisa ser observavel em UMA posicao de adversario.
    candidates = []
    for prev in before.get("seats", []):
        if _is_hero_zone(prev):
            continue
        first = _match_seat(prev, after_a.get("seats", []))
        second = _match_seat(prev, after_b.get("seats", []))
        if first is None or second is None:
            continue
        increase_1 = first[2] - prev[2]
        increase_2 = second[2] - prev[2]
        tolerance = max(2.5, invested_bb * .08)
        # Vencedor recebe aproximadamente as fichas do heroi, descontado
        # rake. Aportes de outros jogadores nao sao atribuidos ao heroi.
        if (increase_1 >= invested_bb * .85 and
                increase_2 >= invested_bb * .85 and
                abs(increase_1 - increase_2) <= tolerance):
            candidates.append(prev)
    if len(candidates) != 1:
        result["reason"] = (
            "Nao foi encontrado exatamente um adversario com ganho "
            "persistente coerente com o pote")
        return result
    # Uma subida visivel do saldo do heroi indicaria premiacao ou side pot.
    for prev in before.get("seats", []):
        if not _is_hero_zone(prev):
            continue
        last = _match_seat(prev, after_b.get("seats", []))
        if last and last[2] > prev[2] + max(2.5, invested_bb * .1):
            result["reason"] = "Heroi tambem ganhou fichas; checar split/side pot"
            return result
    result.update(
        confirmed=True,
        loss_bb=round(float(invested_bb), 2),
        winner=f"adversario em ({candidates[0][0]:.2f}, {candidates[0][1]:.2f})",
        reason="Pote desapareceu e stack de adversario subiu em 2 quadros")
    return result
