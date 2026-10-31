# PLO Trainee — Ciclo 250 (2026-10-31)

## Escopo e entrega publicada

Somente análise offline de gravações PLO5/PLO6. Novo `offline_street_review_draft.py` produz `manual_review_draft.json` a partir de um relatório de evidências por street, **sem confirmar automaticamente nenhuma observação**. Cada decisão nasce como `pending`, valor `null` e justificativa vazia. O validador existente `offline_street_human_review.py` rejeita esse estado até que um revisor declare explicitamente `confirm`, `correct` ou `reject`.

O gerador recompõe o relatório a partir do vídeo e das observações originais, compara o conteúdo armazenado, confere SHA-256, rejeita caminhos inseguros/colisões e publica atomicamente por hard link. Não autoriza OCR, equity, EV, ranges, conselhos em tempo real ou apostas.

## Uso

```bash
python video_analyzer/offline_street_review_draft.py VIDEO.mp4 OBSERVATIONS.json STREET_DIR EMPTY_OUTPUT_DIR
```

Edite todas as decisões `pending`, substitua `reviewer_label` e salve como `manual_review.json`. Depois:

```bash
python video_analyzer/offline_street_human_review.py VIDEO.mp4 OBSERVATIONS.json STREET_DIR manual_review.json EMPTY_REVIEW_OUTPUT_DIR
```

## Testes locais do ciclo

- 1 teste sintético novo para o draft, incluindo FFmpeg, SHA-256, rejeição de `pending`, confirmação explícita e recusa de colisão.
- 14 testes novos de protótipo de formulário HTML offline (ainda **não publicado no repositório**): validação, CSP, escape de dados, colisões, adulteração, sintaxe Node, fluxos Chromium/Playwright e validação do JSON exportado pelo backend.
- 91 testes selecionados passaram após extração independente: 15 novos (14 de formulário e 1 de draft) e 76 execuções de regressão. Não equivalem à suíte integral.
- O Chromium validou o formulário via `page.set_content`; abertura direta `file://` não foi testável neste ambiente por bloqueio administrativo.
- Testes com gravações reais e duração de 40–60 minutos continuam pendentes.

## Próximo ciclo

Publicar o protótipo HTML completo após revisão de segurança e usabilidade, integrar revisão explícita aos recortes MP4, e preparar contrato separado para cálculos condicionais de equity/EV somente com dados revisados e hipóteses registradas.
