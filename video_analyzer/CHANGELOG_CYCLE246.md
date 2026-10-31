# PLO Trainee — Ciclo 246 (2026-10-31)

## Escopo
Somente gravações PLO5/PLO6 offline, até quatro mesas. Não há assistência ao vivo, integração com clientes de poker, simulador jogável ou inferência automática de cartas ocultas.

## Implementado
- `offline_temporal_split_clips.py`: em vez de bloquear todo o clipe que atravessa uma mudança de geometria, divide o intervalo em partes independentes, cada uma usando a região declarada no respectivo segmento temporal. **Não concatena** os trechos e não inventa continuidade.
- Mantém guarda de 0,25 s antes/depois de cada transição interna; intervalos omitidos ficam explícitos em `temporal_split_report.json` e nos JSON por parte. Partes menores que 0,5 s são omitidas.
- Decisões dentro da guarda de transição continuam **bloqueadas integralmente**, mesmo que existam outros quadros seguros no clipe.
- Reaproveita a validação estrita do lote anterior: SHA-256 de vídeo, revisão, lote, clipes e relatórios; verificação de timestamps, geometrias, identidade declarada e autorização humana **declarada**.
- MP4 individuais com overlay explícito de incerteza, metadados por trecho, hash e rollback de arquivos criados em caso de falha.
- `test_offline_temporal_split_clips.py`: 12 testes novos, com geração real FFmpeg e verificação FFprobe; executados junto a 19 testes herdados da classe de regressão.

## Como executar
```bash
python video_analyzer/offline_temporal_split_clips.py VIDEO.mp4 BATCH_DIR TEMPORAL_REVIEW.json EMPTY_OUTPUT_DIR
cd video_analyzer
python -m unittest -v test_offline_temporal_split_clips.TemporalSplitTests
```

## Evidência sintética local
- 31 testes selecionados aprovados (12 novos + 19 herdados).
- Vídeo sintético de 6 s com quatro quadrantes e duas geometrias temporais.
- Quatro MP4 exportados (duas decisões inteiramente seguras e uma decisão atravessando transição dividida em dois trechos); uma decisão próxima da transição bloqueada.
- Transição em 3,0 s: o intervalo 2,75–3,25 s é **omitido e declarado**, não analisado.
- SHA-256 e dimensões dos quatro MP4 conferidos; resultados **não** são avaliações de mãos reais.

## Limitações
- Geometria, identidade das mesas, cartas, ações, ranges e EV não foram validados com gravações reais. Revisão humana é representada por declaração no JSON sintético.
- O algoritmo usa cortes de tempo e coordenadas estáticas por segmento, não tracking de identidade de mesa quadro a quadro.
- Não há teste de sessão real 40–60 min, precisão OCR, Windows ou suíte integral do repositório.
- Falta vídeo autorizado e anotado de 3–5 min para aferir precisão visual; componentes independentes podem avançar.
