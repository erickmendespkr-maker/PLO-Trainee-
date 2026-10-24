# Ciclo 68 — fila offline de intervalos visuais para revisão

Escopo: `docs/VIDEO_ANALYZER_SCOPE.md`. Nenhum jogo ao vivo, integração com poker, aposta, IA adversária ou autorização de decisões estratégicas.

## Implementação

`activity_region_review_queue.py` reaudita o pacote de imagens e o perfil manual de ROIs por meio de `activity_region_change_hints.py` e transforma comparações acima do limiar fixo de pixels em **intervalos para revisão humana**. Compara separadamente até quatro mesas e as regiões hipotéticas `board`, `hero_cards` e `pot`. Só agrupa comparações consecutivas do mesmo ROI e janela quando compartilham exatamente o quadro e o PTS, e quando o intervalo não ultrapassa `--merge-gap-seconds`. Quadros ausentes, comparações sem alteração e mudanças de mesa/janela interrompem o agrupamento.

A fila prioriza apenas pelo **maior valor de diferença média de luminância** (ordem determinística), com orçamento `--max-candidates` e contagem explícita dos intervalos omitidos. Preserva os quadros de origem, PTS decodificados, SHA-256 canônicos do relatório, perfil e pistas e indica `not_calibrated` para layout e significado de poker. Nenhuma diferença de pixel confirma carta, aposta, ação, limite entre mãos, EV ou erro.

## Uso

```bash
python video_analyzer/activity_region_review_queue.py \
  contato_ffmpeg/ perfil_roi_manual.json fila.json \
  --pixel-threshold 0.12 --merge-gap-seconds 2 --max-candidates 100
```

É possível fixar os hashes canônicos dos insumos usando `--expected-report-sha256` e `--expected-profile-sha256`. A saída é criada apenas se não existir; o arquivo de destino não é sobrescrito.

## Testes e bloqueios

`python -m unittest -q test_activity_region_review_queue` cobre quatro mesas sintéticas, proveniência, ordenação determinística, limite de fila, agrupamento temporal, lacunas, ausência de ROI, adulteração de PNG, entradas inválidas, CLI e proteção contra sobrescrita. Testes não equivalem a aferição de OCR ou reconstrução em partidas reais. Falta vídeo autorizado de 3–5 minutos; ainda não há validação com sessões reais de 40–60 minutos.
