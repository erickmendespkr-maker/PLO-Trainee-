# PLO Trainee — Ciclo 245 (2026-10-31)

## Escopo
Somente sessões gravadas, offline/assíncronas, PLO5/PLO6. Sem integração com mesas reais, decisões ao vivo, apostas ou simulador de adversários.

## Entregas
- `offline_temporal_batch_crops.py`: integra lote de clipes de EV **condicional** ao layout temporal de regiões **declarado por revisão humana**. Verifica integridade SHA-256 de vídeo, revisão, lote, MP4 e relatórios de cada decisão. Resolve o segmento do timestamp e verifica **o intervalo inteiro** do clipe, com margem de 0,25 s nas mudanças internas. Bloqueia clipes que cruzam ou se aproximam de uma transição, em vez de usar geometria estática errada. Exporta MP4 por mesa com overlay explícito e JSON de proveniência; produz ledger de clipes exportados/bloqueados. Publicação com hardlinks e rollback de saídas criadas se houver erro.
- `offline_temporal_batch_overview.py`: índice HTML estático/offline com clipes originais e recortes, motivo dos bloqueios e vínculos para relatórios. Antes de publicar, reexecuta a validação de entradas e confere SHA-256 e proveniência de todas as saídas.
- Testes sintéticos para geometria temporal, proteção contra adulteração, colisões, transições, MP4 FFmpeg real, HTML e rollback.

## Execução
```bash
python video_analyzer/offline_temporal_batch_crops.py VIDEO.mp4 BATCH_DIR TEMPORAL_REVIEW.json EMPTY_CROPS_DIR
python video_analyzer/offline_temporal_batch_overview.py VIDEO.mp4 BATCH_DIR TEMPORAL_REVIEW.json CROPS_DIR
python -m unittest -v test_offline_temporal_batch_crops test_offline_temporal_batch_overview
```

## Testes locais verificáveis
- 24 testes novos (19 do exportador e 5 do índice) aprovados.
- 65 testes selecionados aprovados ao incluir 19 do localizador temporal e 22 da revisão temporal anterior.
- Demonstração com vídeo **sintético** de 6 s, 4 mesas e duas geometrias declaradas: 2 MP4 exportados e 2 decisões bloqueadas (`decision_near_uncertain_transition` e `clip_overlaps_or_approaches_geometry_transition`).
- Os arquivos da demonstração foram gerados com FFmpeg e o MP4 inspecionado com FFprobe.

## Limitações
- A revisão humana foi **simulada** nos dados sintéticos; não autentica uma revisão real. Identidade das mesas, cartas, ações, ranges, equity e EV permanecem hipóteses, não fatos observados.
- Sem rastreamento visual de identidade ao mover janelas, sem OCR validado em vídeo real, sem análise real de sessões de 40–60 min, sem teste Windows ou suíte integral.
- Ao cruzar transição, o corte é bloqueado, não segmentado dinamicamente. Próximo passo: dividir cortes em subclipes por segmento ou renderizar geometria temporal quadro a quadro, sempre com revisão humana.
- Falta vídeo autorizado e anotado de 3–5 min para medir acurácia visual; componentes sintéticos podem continuar sem ele.
