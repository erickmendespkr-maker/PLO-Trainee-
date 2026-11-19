# -*- coding: utf-8 -*-
"""Reconstrucao offline de investimento por eventos, feita para PLO Cortes.

Implementacao original. Inspiracao arquitetural: rastrear eventos de stack,
confirmar leituras em quadros consecutivos e separar acoes de premios/rebuys.
Nao faz captura em tempo real, cliques, automacao de sala ou RTA.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
import statistics
from typing import Iterable


@dataclass
class EventoStack:
    segundo: float
    tipo: str
    antes: float
    depois: float
    diferenca_bb: float


@dataclass
class ResultadoFinanceiro:
    confirmado: bool = False
    perda_bb: float | None = None
    investimento_bb: float | None = None
    confianca: str = "insuficiente"
    motivo: str = "Sem leituras de stack suficientes"
    eventos: list[EventoStack] = field(default_factory=list)
    amostras_validas: int = 0
    rebuy_possivel: bool = False
    devolucao_possivel: bool = False


def _numero(x):
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    x = float(x)
    return x if math.isfinite(x) and x >= 0 else None


def _pontos(pontos, bb, minimo=None, maximo=None):
    pares = []
    for entrada in pontos:
        if not isinstance(entrada, (tuple, list)) or len(entrada) != 2:
            continue
        t, s = _numero(entrada[0]), _numero(entrada[1])
        if t is None or s is None or s / bb > 5000:
            continue
        if minimo is not None and t < minimo:
            continue
        if maximo is not None and t > maximo:
            continue
        pares.append((t, s))
    return sorted(pares)


def eventos_de_stack(pontos, bb, tolerancia_bb=0.35, confirmacoes=2):
    """Agrupa patamares consistentes sem converter erros de OCR em apostas.

    Retorna os patamares e suas transicoes. Mantem tempos apenas se o valor
    for confirmado em pelo menos dois quadros. Nao presume o significado
    financeiro de um aumento (pode ser devolucao, premio ou rebuy).
    """
    bb = _numero(bb)
    if not bb or bb <= 0:
        raise ValueError("BB invalido")
    if confirmacoes < 2:
        raise ValueError("Sao necessarias pelo menos duas confirmacoes")
    pontos = _pontos(pontos, bb)
    if not pontos:
        return [], []
    tolerancia = max(bb * tolerancia_bb, 1e-6)
    runs = []
    atual = []
    for t, s in pontos:
        if atual and abs(s - statistics.median(v for _, v in atual)) > tolerancia:
            if len(atual) >= confirmacoes:
                runs.append((atual[0][0], statistics.median(v for _, v in atual)))
            atual = []
        atual.append((t, s))
    if len(atual) >= confirmacoes:
        runs.append((atual[0][0], statistics.median(v for _, v in atual)))
    estados = []
    for t, valor in runs:
        if estados and abs(valor - estados[-1][1]) <= tolerancia:
            continue
        estados.append((t, valor))
    eventos = []
    for (t0, anterior), (t1, posterior) in zip(estados, estados[1:]):
        delta_bb = (posterior - anterior) / bb
        if abs(delta_bb) <= tolerancia_bb:
            continue
        eventos.append(EventoStack(t1,
            "saida" if delta_bb < 0 else "entrada",
            anterior, posterior, round(abs(delta_bb), 2)))
    return estados, eventos


def perda_por_fold(linha_antes: Iterable, linha_durante: Iterable, bb,
                    limite_bb, instante_fold):
    """Confirma perda por FOLD somente com aporte estavel e sem entradas.

    Regra: a perda do heroi e seu investimento nao devolvido. Em caso de
    aumento dentro da mao (rebuy/premio/devolucao indistinguivel), sinaliza
    pendencia em vez de inventar perda. A execucao real deve detectar
    o aviso FOLD separadamente e passar o instante correto.
    """
    ret = ResultadoFinanceiro()
    bb = _numero(bb)
    tempo_fold = _numero(instante_fold)
    if bb is None or bb <= 0 or tempo_fold is None:
        ret.motivo = "BB ou instante do FOLD invalidos"
        return ret
    anteriores = _pontos(linha_antes, bb, maximo=tempo_fold)
    durante = _pontos(linha_durante, bb, maximo=tempo_fold + 0.15)
    ret.amostras_validas = len(durante)
    if len(anteriores) < 1 or len(durante) < 2:
        ret.motivo = "Sem stack antes do jogo ou amostras durante o fold"
        return ret
    base = statistics.median(x for _, x in anteriores)
    estados, eventos = eventos_de_stack(durante, bb)
    ret.eventos = eventos
    if not estados:
        ret.motivo = "Sem dois quadros consecutivos com o mesmo saldo"
        return ret
    if len(anteriores) >= 2:
        if max(x for _, x in anteriores) - min(x for _, x in anteriores) > max(bb, 0.025 * base):
            ret.motivo = "Stack inicial instavel: OCR ou mudanca de mesa"
            return ret
    if any(posterior > anterior + max(bb * 1.0, base * .025)
           for (_, anterior), (_, posterior) in zip(estados, estados[1:])):
        ret.rebuy_possivel = True
        ret.devolucao_possivel = True
        ret.motivo = "Entrada de fichas no meio da mao: rebuy/devolucao nao distinguiveis"
        return ret
    patamar_final = estados[-1][1]
    investido = max(0.0, (base - patamar_final) / bb)
    ret.investimento_bb = round(investido, 2)
    if investido + 1e-7 < limite_bb:
        ret.motivo = "Investimento demonstrado abaixo do limite"
        ret.confianca = "media"
        return ret
    ret.confirmado = True
    ret.perda_bb = round(investido, 2)
    ret.confianca = "alta" if len(anteriores) >= 2 else "media"
    ret.motivo = "FOLD comprovado + patamar de stack estavel sem entrada de fichas"
    return ret
