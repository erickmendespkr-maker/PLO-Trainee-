# Ciclo 161 — vínculo de EV hipotético a clipes offline

## Escopo
Conforme `docs/VIDEO_ANALYZER_SCOPE.md`, este ciclo **não** cria jogo, oponente, integração com mesa ou recomendações em tempo real. Adiciona `offline_reviewed_clip_decision_ev_attachment.py` para anexar relatórios já revisados de EV condicional (`offline_reviewed_decision_ev_link.py`, Ciclo 160) a clipes de mãos já exportados e vinculados (`offline_reviewed_clip_hand_links.py`, Ciclo 159).

## Comportamento implementado
- Revalida SHA-256 da gravação local, relatório de vinculação, relatório do lote, clipes MP4, solicitações e sidecars; recusa links simbólicos e nomes inseguros.
- Confere `hand_id`, `table_id`, PLO5/PLO6, SHA da gravação e do histórico de mãos, limites temporais da mão, do clipe e da decisão.
- Anexa várias decisões hipotéticas a uma mão, ordenadas por timestamp; aceita até 4 mesas e 12 clipes previamente selecionados, com 1–32 relatórios de EV por execução.
- Exige hipóteses explícitas de ranges, probabilidade de fold, valores de EV e intervalos; não infere cartas escondidas ou avalia qualidade real das jogadas.
- Falha sem criar saída em caso de inconsistência e não sobrescreve arquivos existentes. A saída é um novo relatório JSON; os MP4 permanecem intocados.

## Exemplo de uso
```bash
python video_analyzer/offline_reviewed_clip_decision_ev_attachment.py \
  recording.mp4 clip_hand_links.json exported_batch/ new_attachments.json \
  --decision-ev reviewed_decision_ev_link_1.json reviewed_decision_ev_link_2.json
```

## Testes locais
```bash
PYTHONPATH=video_analyzer python -m unittest -v \
  test_offline_reviewed_clip_decision_ev_attachment
```

Executados neste ciclo: **39 testes novos**, incluindo um teste com FFmpeg/FFprobe e vídeo de padrão sintético, e **24 testes selecionados de regressão** do Ciclo 159, total **63 aprovados**. Log local: `selected_tests.log` no pacote do ciclo. Não foi usada GitHub Actions. Não foi executada a suíte completa do repositório.

## Limitações e bloqueios
- O relatório verifica consistência de identidades, janelas e hashes; **não autentica OCR, cartas, ações, pote, ranges ou legalidade de raise**. Mesmo a aprovação humana anterior não é verificação visual independente.
- A incerteza estatística dos resultados Monte Carlo não representa a incerteza dos ranges e hipóteses de ações futuras.
- Ainda não há classificação automática de decisões, legendas incorporadas aos MP4 ou fluxo integrado de interface.
- Falta gravação de PLO5/PLO6 autorizada e anotada de 3–5 minutos para validar o reconhecimento visual; a demonstração é totalmente sintética.
- O motor permanece offline/assíncrono; nenhuma alteração em `main`, produção ou credenciais.
