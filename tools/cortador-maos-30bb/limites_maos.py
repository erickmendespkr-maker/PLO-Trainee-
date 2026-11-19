# -*- coding: utf-8 -*-
"""Limites de maos em gravacoes multi-mesa (offline).

O desaparecimento das cartas do heroi e apenas o fim da sua participacao
visivel. O desfecho do pote pode ocorrer muito depois. Na cronologia
desta gravacao, o limite observavel da mao anterior e a PROXIMA
distribuicao de cartas para o heroi, na MESMA mesa.
"""
from collections import defaultdict


def estender_ate_proxima_distribuicao(candidates, duration):
    """Atualiza limites de recorte sem misturar mesas nem layouts.

    hand_end permanece o instante em que as cartas SUMIRAM para que a
    estimativa de aporte use somente o periodo ativo do heroi.
    next_deal_at marca a proxima distribuicao, se ela foi observada.
    Quando nao ha distribuicao posterior confirmada no mesmo segmento,
    nao inventa o fim da mao.
    """
    groups = defaultdict(list)
    for candidate in candidates:
        if candidate.hand_start is not None:
            groups[(candidate.layout, candidate.table)].append(candidate)
    for hands in groups.values():
        hands.sort(key=lambda c: c.hand_start)
        for i, hand in enumerate(hands):
            segment_end = (hand.segment_end
                           if hand.segment_end is not None else duration)
            following = next(
                (later.hand_start for later in hands[i + 1:]
                 if later.hand_start is not None
                 and later.hand_start > hand.hand_start
                 and later.hand_start < segment_end),
                None)
            hand.next_deal_at = following
            if following is None:
                # Se a proxima distribuicao nao aparece na gravacao,
                # acompanhar a mesa ate terminar o video/segmento. O
                # campo next_deal_at=None permite sinalizar fim incompleto.
                new_end = min(duration, segment_end)
            else:
                # Nao incluir o primeiro quadro da mao seguinte.
                new_end = min(segment_end, following - .15)
            if new_end > hand.start and (
                    hand.hand_end is None or new_end >= hand.hand_end):
                hand.end = new_end
    return candidates
