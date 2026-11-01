# Ciclo 274 — fila offline de revisão OCR por mão

Escopo consultado: `docs/VIDEO_ANALYZER_SCOPE.md`. Somente gravações autorizadas e análise assíncrona/offline; sem mesas jogáveis, oponentes de IA, integração com poker ou decisões ao vivo.

## Entregas

- Publicado `offline_hand_ocr_review_queue.py`, iniciado localmente no ciclo 273 e reforçado com hashes SHA-256 do vídeo, JSONs de origem, quadros e recortes PNG.
- Associa texto OCR **não revisado** a intervalos de mãos **anotados manualmente**, usando mesa e timestamps; observações sem correspondência permanecem explícitas.
- Rejeita paths inseguros, symlinks, intervalos sobrepostos, candidatos duplicados, ROIs fora do recorte, quadros alterados, caminhos de imagens reutilizados e PTS não crescentes.
- Origem PTS é parâmetro explícito, **não autenticado**. Sem promoção automática para fatos, equity, EV ou seleção de clipes.
- Testes autossuficientes geram MP4 sintético e recortes PNG com FFmpeg durante a execução.

## Execução

```bash
python video_analyzer/offline_hand_ocr_review_queue.py VIDEO.mp4 REGION_BUNDLE ORIGINAL_OCR.json HUMAN_HAND_BOUNDARIES.json NEW_QUEUE.json --source-pts-origin 0
```

## Verificação local — 2026-11-01

- 19 testes de unidade executados e aprovados em ambiente local, incluindo geração real de fixture com FFmpeg (testsrc) e três cenários novos de adulteração.
- `py_compile` passou para módulo e testes locais.
- Demonstração sintética preexistente: quatro observações associadas a quatro mesas, nenhuma não associada.
- **Importante:** o teste foi executado contra a versão local antes da publicação. Os arquivos publicados no GitHub não foram baixados e reexecutados byte a byte neste ciclo. Não afirmar validação CI.

## Limitações

- Nenhuma medição de precisão em vídeo real. Falta gravação autorizada e anotada de 3–5 minutos.
- Associação não é reconstrução automática de mãos; a origem temporal e as anotações são declaradas, não autenticadas.
- Auditoria independente de pixels, pipeline completo sampler→Tesseract→OCR e sessões de 40–60 minutos continuam pendentes.
- Não há cálculo de equity/EV neste módulo.
