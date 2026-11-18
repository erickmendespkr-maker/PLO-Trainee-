# -*- coding: utf-8 -*-
"""Contexto de uma mao de PLO5: aporte do heroi, premiacao do pote e rebuy.

Esta validacao e propositalmente conservadora. O stack pre/pos nao prova
perda quando ha recomposicao automatica. Nunca aprovar o corte somente pela
diminuicao do stack, pelo tamanho total do pote ou pelo top-up para 100 BB.
"""
from __future__ import annotations

import math
import re
import unicodedata


def normalize_nick(nick):
    if not isinstance(nick, str):
        return ""
    normal = unicodedata.normalize("NFKD", nick).casefold()
    normal = "".join(c for c in normal if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", normal)


def finite_amount(value, max_value=5000):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, str):
        val = value.strip().replace(",", ".")
        if not re.fullmatch(r"\d{1,5}(?:\.\d{1,3})?", val):
            return None
        value = float(val)
    elif isinstance(value, (int, float)):
        value = float(value)
    else:
        return None
    if not math.isfinite(value) or not 0 <= value <= max_value:
        return None
    return value


def table_context_timestamps(hand_start, hand_end, duration, after_times=None):
    """Oito quadros DURANTE a mao + dois apos o fim para ver o pote entregue.

    Quadros apos o fim podem mostrar recarga. Isso nao e ganho, e apenas
    um marcador que a sessao prosseguiu depois do resultado.
    """
    if not (0 <= hand_start < hand_end < duration - .4):
        return None
    span = hand_end - hand_start
    if span < 2.5:
        return None
    ratios = (.02, .15, .29, .43, .57, .71, .85, .98)
    during = [hand_start + span * p for p in ratios]
    extras = []
    for t in sorted(set(after_times or [])):
        if hand_end + .01 < t < duration:
            extras.append(float(t))
    if len(extras) >= 2:
        aftermath = [extras[0], extras[min(len(extras)-1, 2)]]
    else:
        aftermath = [
            min(duration - .05, hand_end + .5),
            min(duration - .03, hand_end + 2.0),
        ]
    if aftermath[1] <= aftermath[0]:
        return None
    return during + aftermath


def validate_pot_result(payload, expected_nick, threshold=30):
    """Retorna evidencia validada sem assumir stack inicial de 100 BB.

    A IA deve identificar o TOTAL investido pelo proprio heroi nesta mao,
    e confirmar que o resultado foi para outro jogador, sem side pot ganho
    pelo heroi. Pote >30 BB NAO implica investimento >30 BB.
    """
    base = {
        "verified": False, "loss_bb": None, "hero_invested_bb": None,
        "pot_winner": None, "auto_rebuy_seen": None,
        "reason": "Analise da mesa inconclusiva", "evidence": ""
    }
    if not isinstance(payload, dict):
        return base
    evidence = payload.get("evidence")
    if isinstance(evidence, str):
        base["evidence"] = evidence[:420]
    base["auto_rebuy_seen"] = (
        payload.get("auto_rebuy_seen")
        if type(payload.get("auto_rebuy_seen")) is bool else None)
    winner = payload.get("winner_nick")
    if isinstance(winner, str):
        base["pot_winner"] = winner[:100]
    expected = normalize_nick(expected_nick)
    hero = normalize_nick(payload.get("hero_nick"))
    if not expected or not hero or expected != hero:
        base["reason"] = "Nick do jogador nao identificado com seguranca"
        return base
    if payload.get("same_hand") is not True:
        base["reason"] = "Os quadros nao confirmam uma unica mao"
        return base
    if payload.get("hand_finished") is not True:
        base["reason"] = "Nao ficou claro que a mao terminou"
        return base
    if payload.get("pot_awarded_to_opponent") is not True:
        base["reason"] = "Premiacao do pote a outro jogador nao confirmada"
        return base
    if payload.get("hero_won_any_pot") is not False:
        base["reason"] = "Side pot ou parte do pote do heroi nao descartado"
        return base
    if not winner or normalize_nick(winner) == expected:
        base["reason"] = "Vencedor adversario nao identificado com seguranca"
        return base

    committed = finite_amount(payload.get("hero_invested_bb"))
    if committed is None:
        base["reason"] = "Contribuicao do heroi ao pote nao foi quantificada"
        return base
    base["hero_invested_bb"] = round(committed, 2)

    if committed + 1e-6 < threshold:
        base["reason"] = "Investimento do heroi abaixo do limite"
        return base
    if payload.get("investment_visibly_verified") is not True:
        base["reason"] = "Valor investido nao sustentado por evidencias visuais"
        return base

    base["verified"] = True
    base["loss_bb"] = round(committed, 2)
    base["reason"] = "Aporte do heroi perdido para outro jogador, sem pote recuperado"
    return base
