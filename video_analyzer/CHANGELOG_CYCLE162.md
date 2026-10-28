# Ciclo 162 — fila conservadora de revisão de decisões por EV hipotético

## Escopo
Conforme `docs/VIDEO_ANALYZER_SCOPE.md`, este ciclo adiciona apenas um **ordenador offline para revisão humana**. Não cria mesas jogáveis, assistência em tempo real, adversários artificiais, integração com poker real, nem recomendações de apostas.

## Implementação
`offline_reviewed_ev_review_priority.py` recebe a gravação local, diretório de MP4 exportados e relatório de decisões do Ciclo 161. Confere SHA-256 da gravação, de cada clipe e do relatório de entrada, identidade de mãos/mesas, timestamps, PLO5/PLO6, hipóteses explícitas e intervalos de EV. Rejeita JSON com chaves duplicadas/NaN, links simbólicos, caminhos inseguros, contagens divergentes, intervalos inválidos, arquivos alterados, identidade duplicada e saída já existente.

Para cada decisão, compara o intervalo de EV **condicional** da ação observada com os intervalos das alternativas fold/call/raise. Registra:
- `positive_interval_separation_units`: maior separação inferior positiva de uma alternativa contra a ação observada (somente sob o modelo declarado).
- `possible_gap_upper_units`: maior diferença superior possível de uma alternativa contra o limite inferior da ação observada.
- `review_label`: `model_interval_separated_manual_review`, `overlapping_intervals_manual_review` ou `no_positive_model_gap_detected`.

Ordena primeiro a separação condicional, depois o potencial máximo, com desempates determinísticos. **Nenhum rótulo é prova de erro**: ranges, OCR, ações futuras, side pots, rake, legalidade de raises e potes reais não foram autenticados. A incerteza do modelo não está contida nos intervalos de amostragem Monte Carlo. Os relatórios mantêm `automatic_clip_selection_authorized=false`, `action_recommendation_authorized=false` e `decision_quality_verified=false`. Os MP4 nunca são modificados.

## Execução
```bash
python video_analyzer/offline_reviewed_ev_review_priority.py \
  recording.mp4 exported_batch/ clip_decision_ev_attachments.json \
  manual_review_priority.json --min-separation 0
```

## Testes executados
- 34 testes novos com `unittest` (incluindo teste FFmpeg/FFprobe real de vídeo sintético).
- 39 testes selecionados de regressão do módulo do Ciclo 161.
- **73 testes aprovados** em ambiente local; nenhum GitHub Actions utilizado.
- Demonstração com MP4 sintético do Ciclo 161: 1 decisão `overlapping_intervals_manual_review`, separação inferior 0 e diferença superior possível 73,58 fichas; nenhuma recomendação gerada.

## Limitações e bloqueios
O novo módulo não recalcula EV nem reabre arquivos originais de auditoria do Ciclo 160: ele verifica apenas hashes do relatório de anexos, da gravação e dos MP4 locais. O resultado é uma fila de **candidatos para revisão humana**, não seleção automática de clipes ou avaliação comprovada da jogada. Não foi executada a suíte completa do repositório. Falta gravação de PLO5/PLO6 autorizada e anotada de 3–5 minutos para medir OCR/visão; sessões reais de 40–60 minutos ainda não foram validadas.