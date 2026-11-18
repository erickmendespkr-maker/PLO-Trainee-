# -*- coding: utf-8 -*-
"""Triagem PLO offline, SEM rede: estimativa do aporte do heroi no pote.

IMPORTANTE: stack que caiu durante a mao NAO prova que o heroi perdeu.
Rebuy para 100BB tambem NAO prova resultado. Somente historico oficial
confiavel ou verificacao humana da premiacao valida o prejuizo.
"""
from __future__ import annotations

import math
import statistics


def times_for_hand(candidate, video_duration, inside_samples=7):
    """Uma leitura antes, ate 7 durante e uma apos a mao; custo limitado."""
    if not 1 <= inside_samples <= 15:
        raise ValueError("Quantidade de amostras invalida.")
    start = (candidate.hand_start if candidate.hand_start is not None
             else max(0., candidate.start + 5.))
    end = (candidate.hand_end if candidate.hand_end is not None
           else candidate.end - 5.)
    if not 0 <= start < end <= video_duration:
        return None
    before = sorted(t for t in candidate.before_times if 0 <= t < start)
    after = sorted(t for t in candidate.after_times if end < t < video_duration)
    before_time = before[-1] if before else max(0.01, start - 1.5)
    if before_time >= start:
        return None
    points = [start + (end - start) * (i + .5) / inside_samples
              for i in range(inside_samples)]
    after_time = after[0] if after else min(video_duration - .01, end + 1.5)
    if after_time <= end:
        return None
    return {"before": [before_time], "during": points, "after": [after_time]}


def assess_stacks(before, during, after, bb, threshold):
    """Conservador: oferece PRIORIDADE de revisao, nunca perda confirmada.

    before/during/after sao listas numericas com None quando OCR falhou.
    Somente interpreta o menor stack durante a mao como um INDICIO de
    contribuicao; nao deduz vencedor, side pots, refunds ou saldo de 100BB.
    """
    result = {
        "prioritize": False, "invested_estimate_bb": None,
        "baseline_bb": None, "minimum_bb": None,
        "rebuy_possible": False, "reason": "OCR insuficiente para estimar o aporte",
    }
    if not isinstance(bb, (int, float)) or not math.isfinite(bb) or bb <= 0:
        return result

    def clean(values):
        return [float(x) for x in values if isinstance(x, (int, float))
                and not isinstance(x, bool) and math.isfinite(x)
                and 0 <= x / bb <= 5000]
    initial = clean(before)
    intra = clean(during)
    final = clean(after)
    if not initial or len(intra) < 2:
        return result
    baseline = statistics.median(initial)
    # Um zero isolado costuma ser OCR defeituoso; all-in deve aparecer em
    # mais de uma amostra para ser considerado evidência mínima.
    valid_low = []
    for x in intra:
        if x > 0 or sum(v == 0 for v in intra) >= 2:
            valid_low.append(x)
    if len(valid_low) < 2:
        return result
    floor = min(valid_low)
    if floor > baseline:
        result["reason"] = "Stack cresceu durante a mao; sem aporte demonstrado"
        return result
    committed = max(0.0, (baseline - floor) / bb)
    result.update({
        "invested_estimate_bb": round(committed, 2),
        "baseline_bb": round(baseline / bb, 2),
        "minimum_bb": round(floor / bb, 2),
    })
    if final:
        closing = statistics.median(final) / bb
        result["rebuy_possible"] = (closing > floor / bb + 15
                                    and abs(closing - 100) < 3)
    if committed + 1e-6 >= threshold:
        result["prioritize"] = True
        result["reason"] = (
            "Possivel aporte >= limite observado no stack durante a mao; "
            "CONFIRMAR o adversario recebendo o pote")
    else:
        result["reason"] = (
            "Aporte minimo estimado abaixo do limite, mas as amostras "
            "podem ter perdido apostas entre quadros")
    return result


def offline_review_decision(amount_bb, threshold, pot_destination):
    """Apenas confirmacao humana explicita aprova clip como PERDA.

    pot_destination: 'oponente_tudo', 'hero_parte', 'hero_tudo', 'incerto'.
    """
    if pot_destination != "oponente_tudo":
        return False
    if isinstance(amount_bb, bool) or not isinstance(amount_bb, (int, float)):
        return False
    return math.isfinite(amount_bb) and amount_bb >= threshold and amount_bb > 0
