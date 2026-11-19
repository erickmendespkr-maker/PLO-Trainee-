# -*- coding: utf-8 -*-
"""Diagnostico offline de relatorio_analise.csv, sem Gemini e sem video."""
import argparse
import csv
import json
from collections import Counter


def analisar(path):
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh, delimiter=";"))

    def number(value):
        try:
            return float(str(value).replace(",", "."))
        except (TypeError, ValueError):
            return None

    folds = sum(row.get("fold_encontrado", "").upper() == "SIM"
                for row in rows)
    losses = sum((number(r.get("perda_bb")) or 0) >= 30 for r in rows)
    potentials = sum((number(r.get("aporte_heroi_bb")) or 0) >= 30
                     and not r.get("perda_bb") for r in rows)
    unread = sum(number(r.get("fold_ocr_melhor_confianca")) in
                 (None, -1) for r in rows)
    output = {
        "maos": len(rows),
        "folds_encontrados": folds,
        "perdas_30bb_confirmadas": losses,
        "aportes_30bb_pendentes": potentials,
        "fold_sem_leitura_visual": unread,
        "estados": dict(Counter(row.get("status", "").split(" - ")[0]
                               for row in rows)),
        "recomendacoes": (
            (["Conferir area FOLD sobre o avatar e OpenCV instalado"]
             if not folds else []) +
            (["Revisar aportes, devolucoes e rebuys nos candidatos pendentes"]
             if potentials else [])
        )
    }
    return output


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", nargs="?", default="relatorio_analise.csv")
    args = ap.parse_args()
    print(json.dumps(analisar(args.csv), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
