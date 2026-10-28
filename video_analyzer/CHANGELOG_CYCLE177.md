# Ciclo 177 — linha do tempo conservadora de ações e apostas

Escopo: `docs/VIDEO_ANALYZER_SCOPE.md`. Apenas sessões gravadas de PLO5/PLO6, até quatro mesas. Sem jogo ao vivo, captura de mesas, adversários de IA ou execução de apostas.

## Entregas

- `offline_action_bet_timeline.py`: recebe `hand_drafts.json` do Ciclo 174/176 e produz um JSON de **evidências OCR revisadas**, ordenadas por timestamp e mesa, com `proposal_index`, valor, revisão e fase aproximada do board observado.
- Reúne ações com observações de aposta próximas (janela de **2 segundos**) sem inferir que pertencem ao mesmo jogador ou que representam contribuição efetiva ao pote.
- Sinaliza ausência de ações/board, OCR pendente, regressão de board, pote decrescente, valores de pote conflitantes no mesmo timestamp, ações simultâneas conflitantes e aposta OCR próxima de múltiplas ações.
- Exige proveniência SHA-256 do rascunho e seus relatórios de origem, valida limites e identidades das mãos, cartas, valores, timestamps, índices OCR, sobreposição na mesma mesa e JSON com chaves duplicadas ou NaN. Não sobrescreve arquivos existentes.
- `test_offline_action_bet_timeline.py`: 30 testes sintéticos.

## Reprodução local

```sh
cd video_analyzer
python -m unittest -v test_offline_reviewed_hand_drafts.py test_offline_hand_temporal_consistency.py test_offline_hand_timeline_review.py test_offline_boundary_annotation_import.py test_offline_timeline_import_browser.py test_offline_action_bet_timeline.py
python offline_action_bet_timeline.py RASCUNHOS/hand_drafts.json NOVO_RELATORIO.json
```

## FEITO E TESTADO

- **111/111 testes locais aprovados**: 81 regressões dos ciclos anteriores e 30 testes novos, incluindo FFmpeg e Chromium sintéticos nos testes de integração já existentes.
- Integração com `demo/rebuilt/hand_drafts.json` do pacote do Ciclo 176: 2 mãos, uma com 1 observação de pote e outra sem campos confirmados; ambos os relatórios exigem revisão e mantêm `ready_for_equity_or_ev=false`.
- Verificados hashes Git blob SHA-1 dos arquivos Python publicados, coincidentes com os arquivos locais testados.
- Nenhum GitHub Actions executado.

## NÃO VERIFICADO

- Reconstrução de apostas por jogador/posição, legalidade das ações, pote matematicamente reconciliado, ranges, equity ou EV.
- O texto de ação OCR pode representar botão, ação de outro jogador ou estado temporário da interface; a associação por 2 segundos é somente uma pista visual.
- Fase do board é apenas a última observação visível, **não** prova de que a ação ocorreu naquela street; `street_unknown` não equivale a preflop.
- Suíte completa do repositório, Windows, vídeos reais e sessões completas de 40–60 minutos.

## PENDÊNCIA EXTERNA

Gravação autorizada e anotada de PLO5/PLO6 com 3–5 minutos para avaliar precisão do OCR, delimitação de mãos e sequência de ações.

## PRÓXIMO CICLO

Criar pacote offline de revisão visual que vincule cada evento aos recortes de ROI com hash conferido, sem carregar caminhos arbitrários nem liberar equity/EV. Depois, validar transições por street e contribuições por jogador somente quando a evidência permitir.
