# Ciclo 184 — triagem offline de ações OCR para revisão

## Entrega

Novo `offline_action_review_triage.py`: lê a saída de `offline_action_bet_timeline.py` e organiza **observações OCR de ações** por prioridade de revisão humana. Cada candidato preserva mesa (1–4), PLO5/PLO6, mão, timestamp, índice da observação, índices de OCR de aposta/pote próximos, avisos e janela sugerida de pré-visualização dentro da mão. A saída inclui SHA-256 do JSON de origem e não sobrescreve arquivos existentes.

O ranking é **heurístico, não matemático**: categoria da ação OCR (check=1, fold=2, call=3, bet=4, raise=5, all-in=6), alertas presentes (+2), OCR não resolvido (+2) e ausência de OCR de pote próximo (+1). Esses pontos não são fichas, probabilidades, equity, EV ou comprovação de erro estratégico. O sistema não identifica o jogador, não verifica a legalidade das apostas e não autoriza exportação de clipes sem revisão dos limites.

## Execução

```bash
python video_analyzer/offline_action_bet_timeline.py HAND_DRAFTS_JSON NEW_TIMELINE_JSON
python video_analyzer/offline_action_review_triage.py NEW_TIMELINE_JSON NEW_QUEUE_JSON
python -m pytest -q video_analyzer/test_offline_action_review_triage.py video_analyzer/test_offline_action_bet_timeline.py
```

A fixture `synthetic_four_tables_review_fixture.json` está no repositório, com quatro mesas artificiais, duas PLO5 e duas PLO6. Os testes locais dos dois módulos totalizaram **46 aprovados** (16 novos e 30 regressões). Uma integração adicional com a saída sintética do módulo anterior gerou oito candidatos. Nenhum teste usa sessão real.

## Limitações

Ainda faltam reconstrução completa de mãos, atribuição de jogadores, ranges, equity Monte Carlo, EV e seleção por impacto matemático. A janela de pré-visualização não substitui a revisão humana de limites de clipes. Não foram executados testes no Windows, sessões reais de 40–60 minutos ou suíte integral do repositório. Falta vídeo autorizado/anotado de 3–5 minutos para calibrar OCR. Nenhum GitHub Actions, produção, credencial ou `main` foi alterado.
