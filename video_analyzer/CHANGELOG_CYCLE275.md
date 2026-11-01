# Ciclo 275 — origem PTS medida pelo FFmpeg

## Escopo
Somente a branch `feature/plo5-plo6-training`, conforme `docs/VIDEO_ANALYZER_SCOPE.md`. Nenhuma captura ao vivo, mesa jogável, apostas ou integração com plataformas de poker.

## Implementação
- `offline_verified_pts_review_queue.py`: usa FFprobe para obter início do stream de vídeo e duração; usa **FFmpeg com `-copyts`** e `showinfo` para medir o PTS do primeiro quadro decodificado. Sem `-copyts`, FFmpeg pode rebater um PTS de 5 segundos para zero, provocando uma associação incorreta entre OCR e mãos.
- Chama o módulo existente `offline_hand_ocr_review_queue.build`, sem alterar seus bloqueios de OCR, equity/EV ou clipes automáticos.
- Verifica o hash SHA-256 da gravação, a duração quando informada no manifesto, os PTS das amostras dentro da linha temporal medida, o replay independente dos seeks FFmpeg quando o manifesto informa `requested_seek_seconds` e a coerência do primeiro PTS com o início informado pelo FFprobe (tolerância de 0,5 s).
- Publica JSON novo exclusivamente após validação. Não sobrescreve resultados anteriores.

## Testes locais verificáveis

```bash
cd video_analyzer
python -m unittest -v test_offline_hand_ocr_review_queue test_offline_verified_pts_review_queue
```

34 testes locais passaram: 19 existentes + 15 novos. FFmpeg 7.1.5 e FFprobe reais foram executados. Teste sintético de quatro regiões com PTS zero e teste com PTS inicial de 5 segundos gerado com `setpts=PTS+5/TB` passaram. Os testes não substituíram FFmpeg/FFprobe por mocks. O replay detectou um PTS artificialmente adulterado em 0,25 segundo e validou um seek com origem de 5 segundos. O Tesseract não foi executado nesta suíte; as propostas OCR do fixture são sintéticas.

## Uso

```bash
python video_analyzer/offline_verified_pts_review_queue.py \
  gravacao.mp4 pacote_regioes propostas_ocr.json limites_humanos.json novo_relatorio.json
```

## Limites
A origem temporal é aferida a partir do primeiro quadro de vídeo e do início do stream, não da precisão semântica do OCR. A origem dos pixels dos recortes e a precisão das anotações humanas exigem auditorias independentes. A cadeia original completa de geração de amostras + Tesseract + associação OCR não foi reexecutada nesta etapa. Não foram testados vídeos reais de PLO5/PLO6 nem sessões de 40–60 minutos. Os campos OCR permanecem pendentes de revisão humana; equity/EV e seleção automática de clipes permanecem bloqueados.
