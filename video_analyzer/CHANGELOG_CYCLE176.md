# Ciclo 176 — revisão offline e reimportação segura dos limites das mãos

Escopo: `docs/VIDEO_ANALYZER_SCOPE.md`. Apenas vídeos gravados, sem mesa jogável, adversários de IA, captura ao vivo, apostas ou integração com plataformas de pôquer.

## Publicado na branch `feature/plo5-plo6-training`

- `offline_hand_timeline_review.py`: publicação do protótipo local do Ciclo 175, com relatório HTML/JSON, seleção local de MP4/WebM, navegação por timestamp e exportação de anotações. A exportação agora impede mudanças de limites em estados `pending`, `confirmed` ou `inconclusive`; `corrected` exige mudança e justificativa.
- `offline_boundary_annotation_import.py`: importador offline que exige o SHA-256 exato do rascunho, identidade de cada mão, vínculo com o relatório OCR revisado, campos JSON estritos, tempos finitos, justificativa para correções e ausência de sobreposição por mesa. Emite `revised_boundaries.json` compatível com o construtor do Ciclo 174 e `boundary_review_audit.json` com proveniência e estados de revisão.
- `test_offline_hand_timeline_review.py`: 22 testes da interface e da validação temporal, incluindo Chromium headless.
- `test_offline_boundary_annotation_import.py`: 26 testes de contrato, adulteração, revisão, SHA, não sobrescrita e reconstrução de rascunho.
- `test_offline_timeline_import_browser.py`: 3 testes de integração usando vídeo sintético FFmpeg H.264, Chromium, exportação JSON, importação e reconstrução de rascunho.

## Reprodução local

Na pasta `video_analyzer`:

```sh
python -m unittest -v test_offline_reviewed_hand_drafts.py test_offline_hand_temporal_consistency.py test_offline_hand_timeline_review.py test_offline_boundary_annotation_import.py test_offline_timeline_import_browser.py
python offline_hand_timeline_review.py HAND_DRAFTS_JSON NOVA_PASTA_TIMELINE
# Abrir NOVA_PASTA_TIMELINE/hand_timeline_review.html, selecionar vídeo gravado e exportar JSON.
python offline_boundary_annotation_import.py HAND_DRAFTS_JSON ANNOTATIONS_JSON REVIEWED_OCR_JSON NOVA_PASTA_IMPORT
python offline_reviewed_hand_drafts.py REVIEWED_OCR_JSON NOVA_PASTA_IMPORT/revised_boundaries.json NOVA_PASTA_RASCUNHOS
```

## FEITO E TESTADO

- **81/81 testes locais aprovados** após publicar os cinco arquivos de código/teste, usando versões locais com Git blob SHA-1 coincidente com os arquivos remotos. Inclui 18 testes do Ciclo 174, 12 do módulo temporal, 22 da interface, 26 do importador e 3 de integração navegador/FFmpeg.
- Demonstração sintética com duas mãos em mesas diferentes: uma correção de 0,0 para 0,5 s e outra pendente. Reimportação gerou novos rascunhos e preservou `ready_for_equity_or_ev=false`.
- Nenhum GitHub Actions executado.

## NÃO VERIFICADO

- Suíte integral do repositório, Windows, segurança de execução em todos os navegadores, precisão de OCR e segmentação em gravações reais, sessões completas de 40–60 min, reconstrução de ações/apostas e equity/EV em mãos reais.
- SHA-256 comprova correspondência dos bytes, não autoria nem veracidade da revisão humana. O estado `confirmed` é apenas uma anotação do usuário, não valida automaticamente a mão.
- Revisão de limites não valida cartas ocultas, ranges, pote ou sequência de apostas. Mesmo após reconstrução de rascunho, EV continua bloqueado.

## PENDÊNCIA EXTERNA

Vídeo autorizado e anotado de 3–5 minutos para medir acurácia visual.

## PRÓXIMO CICLO

Criar validação temporal específica de ações e apostas por street, associando OCR, PTS e alertas de incoerência. Em seguida, preparar pacote de revisão visual que mostre recortes de ROI ao lado dos eventos, sem promover observações incertas a fatos.
