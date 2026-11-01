# Ciclo 260 — auditoria independente de pixels ROI

## Escopo
Apenas vídeos gravados offline PLO5/PLO6. Nenhuma mesa jogável, assistência em tempo real, integração com sites de pôquer ou apostas. Conforme `docs/VIDEO_ANALYZER_SCOPE.md`.

## Entrega
- `offline_ingest_roi_pixel_audit.py` executa primeiro a auditoria de PTS, geometria, tamanho e SHA-256 de `offline_ingest_pts_audit.py`.
- Identifica o índice absoluto de cada quadro pelo timestamp FFprobe, com tolerância de 2 ms, e redecodifica o quadro do vídeo original com FFmpeg.
- Compara o recorte JPEG declarado com a região correspondente no quadro redecodificado, usando erro médio absoluto RGB (limiar de protótipo: 12).
- Agrupa as quatro mesas por índice de quadro para evitar decodificações repetidas da mesma imagem; limita a 64 amostras por execução.
- Relatório JSON com índice do quadro, PTS e erro de cada ROI; `ocr_verified=false`, `hands_reconstructed=false`, `equity_ev_authorized=false`.
- Rejeita recorte trocado por outra mesa mesmo quando o manifesto tem SHA-256 recalculado, situação que a auditoria apenas de hash/PTS não detectava.

## Verificação local
`python -m unittest -v test_offline_ingest_pts_audit.py test_offline_ingest_roi_pixel_audit.py`

Resultado: **24/24 testes aprovados** (13 anteriores + 11 novos), usando FFmpeg/FFprobe e vídeo VFR sintético de quatro quadrantes. O caso adversarial de JPEG de outra mesa com hash atualizado foi aceito pela auditoria anterior, mas bloqueado pela nova comparação de pixels. Os hashes Git dos dois arquivos Python publicados foram conferidos contra os arquivos locais executados.

## Limitações e bloqueios
- Os testes não executaram `offline_video_ingest_probe.build` original; as amostras foram construídas sinteticamente com FFmpeg.
- Reprocessar desde o início até cada quadro pode ser caro em sessões longas. Não há benchmark Full HD nem de 40–60 minutos para esta nova auditoria.
- Similaridade de pixels não comprova OCR, identidade semântica de mesa, cartas, mãos ou ações; o limiar não foi calibrado com gravações reais.
- Falta vídeo autorizado e anotado de 3–5 minutos. Nenhuma métrica de precisão real pode ser afirmada.

## Próximo ciclo
Testar `offline_video_ingest_probe.build` original com a nova auditoria no mesmo pipeline; medir custo de redecodificação e criar estratégia de decodificação agrupada/seek para vídeos longos, preservando PTS.
