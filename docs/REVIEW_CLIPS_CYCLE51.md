# PLO Trainee — cortes MP4 com seleção humana (ciclo 51)

Escopo: gravações offline PLO5/PLO6, até quatro mesas. Esta etapa **não** reconhece cartas automaticamente, não autoriza equity/EV e não identifica erros objetivos.

Fluxo: fila de decisões revisadas → rascunho do editor → template de seleção → aprovação manual da ação e das regiões → cortes FFmpeg por mesa → manifesto de proveniência.

1. Gere a seleção com `python video_analyzer/activity_review_clip_template.py video.mp4 queue.json draft.json selection.json`.
2. Confira as regiões da gravação e defina `regions_human_confirmed=true`; escolha os eventos desejados, marque `reviewer_approved=true`, informe `reviewer_priority` (0–1) e uma `explanation` humana.
3. Exporte com `python video_analyzer/activity_review_clip_export.py video.mp4 queue.json draft.json selection.json clips_revisados`.

O template é **não aprovado** por padrão. A prioridade é manual, não EV modelado. Os SHA-256 vinculam bytes e JSON, não autenticam a veracidade das anotações. A exportação cria um diretório novo e registra os hashes dos MP4. Requer FFmpeg e FFprobe. Testes sintéticos: `python -m unittest test_activity_review_clip_export test_activity_review_clip_template` executado dentro de `video_analyzer`.

**Bloqueio:** falta vídeo autorizado de PLO5/PLO6 de 3–5 minutos para medir OCR, segmentação e reconstrução reais.
