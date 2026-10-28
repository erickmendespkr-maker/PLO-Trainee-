# Ciclo 179 — vincular cortes MP4 a limites de mãos revisados

Escopo consultado: `docs/VIDEO_ANALYZER_SCOPE.md`. Somente gravações offline PLO5/PLO6; sem mesa jogável, integração com poker real ou assistência ao vivo.

## Publicado na branch feature/plo5-plo6-training

- `offline_clip_review_gate.py`: recebe vídeo local, rascunho de mão, relatório de revisão de limites gerado pelo importador do Ciclo 176, ID da mão e crop manual. Só libera requisições para mãos marcadas como `confirmed` ou `corrected` e consistentes com os limites originais.
- Emite `request.json` compatível com o exportador individual `offline_reviewed_clip_export.py` já existente e `provenance.json` com SHA-256 dos insumos. A saída é um diretório novo, criado ao final da validação.
- Bloqueia revisões pendentes/inconclusivas, hashes divergentes, limites fora da duração, recortes inválidos, symlinks e JSON com chaves duplicadas ou NaN. Não altera o vídeo original.
- `test_offline_clip_review_gate.py`: 16 testes sintéticos, incluindo FFprobe real, limites corrigidos, integridade e entradas inválidas.

## Uso

```sh
cd video_analyzer
python offline_clip_review_gate.py VIDEO.mp4 hand_drafts.json boundary_review.json H1 crop.json NOVO_DIRETORIO
python offline_reviewed_clip_export.py VIDEO.mp4 NOVO_DIRETORIO/request.json NOVO_CLIP.mp4
python -m unittest -v test_offline_clip_review_gate
```

O crop é manual em pixels pares: `{"x":0,"y":0,"width":320,"height":180}`. O rótulo de revisão é uma afirmação humana, não prova de que os limites da mão estão corretos. `request.json` mantém a estrutura do exportador já existente; `provenance.json` deve ser conservado junto ao MP4.

## FEITO E TESTADO

- 16 testes novos e 257 testes selecionados dos ciclos anteriores e do protótipo local: 273/273 aprovados no ambiente local após publicação dos dois arquivos Python.
- Demonstração sintética com FFmpeg: vídeo de 6 s, recorte da região de mesa 4 (320×180) e MP4 final de 2,000 s, com hashes SHA-256 registrados. A geração do clipe de demonstração foi feita com comando FFmpeg direto, **não** pela integração completa com o exportador remoto.
- SHA Git dos dois arquivos Python publicados conferido com os arquivos testados localmente.
- Nenhum GitHub Actions, custo, credencial ou alteração na `main`.

## NÃO VERIFICADO

- Integração de ponta a ponta entre o novo gate e o exportador individual publicado, nem execução em Windows.
- Vídeos reais de 40–60 minutos, precisão de OCR, segmentação de mãos, crops automáticos, ranges, equity, EV e explicações matemáticas.
- O vídeo não está criptograficamente vinculado ao vídeo que originou o OCR. A confiança de reconhecimento não está calibrada.
- Existe um protótipo local independente `offline_reviewed_clip_export.py` com exportação em lote e 30 testes sintéticos; **não foi publicado neste ciclo** para evitar substituir o exportador individual existente na branch.

## PENDÊNCIA EXTERNA

Vídeo autorizado e anotado de PLO5/PLO6 de 3–5 minutos para aferir reconhecimento e segmentação. O trabalho sintético pode prosseguir.

## PRÓXIMO CICLO

Integrar gate + exportador individual em teste end-to-end usando exatamente os arquivos do GitHub; reforçar vínculo do vídeo com frames/ROI de origem; adicionar prévia de clipes ao visualizador offline e preparar modelo matemático condicionado a dados completos.
