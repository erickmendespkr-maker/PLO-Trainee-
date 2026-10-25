# PLO Trainee — Ciclo 92 (25/10/2026)

## Objetivo e escopo
Somente a branch `feature/plo5-plo6-training`. Plataforma offline/assíncrona para sessões PLO5/PLO6 gravadas, sem assistência em tempo real, apostas, simulador ou adversários jogáveis. O escopo de referência é `docs/VIDEO_ANALYZER_SCOPE.md`.

## Implementado
`hand_action_visual_verdicts.py` adiciona uma etapa explícita de revisão humana das evidências visuais auditadas pela galeria do ciclo 91.

- Reconstrói o relatório da galeria a partir do vídeo, navegação, revisão, relatório de auditoria, imagens PNG e regiões de mesas, conferindo hashes e consistência antes de aceitar a fonte.
- Gera formulário JSON por campo/ação, preservando mesa, identificador, PTS solicitado, SHA-256 da imagem e SHA-256 da galeria.
- Apenas anotações humanas com quadro próximo auditado recebem `pending`. Hipóteses, dados desconhecidos e quadros não auditados permanecem `unreviewable`.
- O revisor pode registrar `confirmed_visual`, `rejected_visual` ou `uncertain`, com identidade, justificativa e confiança subjetiva entre 0 e 1.
- Valida novamente o formulário contra os dados imutáveis originais; rejeita troca de mesa, PTS, SHA, ordenação, anotações inventadas, valores não finitos e tentativas de ativar autorização matemática.
- Gera relatório JSON de vereditos e contagens. Todos os sinalizadores de autorização para equity, EV, identificação de erros e seleção automática de clipes permanecem **false**.
- Não altera o histórico de mãos nem confirma reconstrução completa; uma inspeção visual isolada não comprova a estratégia correta.

## Uso local
A partir de `video_analyzer/`, com as saídas verificadas dos ciclos 90–91:

```bash
python hand_action_visual_verdicts.py template VIDEO.mp4 navigation.json review.json stills/ gallery/ visual_review_template.json --regions-json regions.json
# Editar uma cópia do JSON: verdict, reviewer, notes, visual_confidence.
python hand_action_visual_verdicts.py finalize VIDEO.mp4 navigation.json review.json stills/ gallery/ visual_review_edited.json visual_verdicts.json --regions-json regions.json
```

As saídas precisam ser arquivos novos. Para uma gravação com quatro mesas, forneça `--regions-json`.

## Verificação local reproduzível
Ambiente: Python 3.13.5; FFmpeg 7.1.5; testes `unittest` com vídeo sintético de quatro segundos.

- `python -m unittest -q test_hand_action_visual_verdicts`: **14 aprovados**.
- `python -m unittest -q test_hand_action_visual_verdicts test_hand_action_review_gallery test_boundary_hand_draft test_boundary_history_bridge`: **54 aprovados**.
- `python -m unittest -q test_hand_action_pts_evidence`: **15 aprovados**.
- Repetição dos 14 testes novos em extração limpa do snapshot do ciclo 91 com os dois arquivos novos: **14 aprovados**.

As contagens de 54 e 15 são conjuntos separados, mas não representam a suíte completa. Não foi verificado CI remoto. Os dois arquivos de código/teste publicados possuem os mesmos SHA Git blob das cópias locais testadas.

## Demonstração sintética
Quatro mesas, 24 anotações: 8 elegíveis e 16 não revisáveis. Um veredito sintético `uncertain` produz 7 pendentes, 1 incerto, 16 não revisáveis e nenhuma confirmação de mão. As imagens são artificiais, sem poker real.

## Bloqueios e próximos passos
Falta um vídeo autorizado de 3–5 minutos com anotações humanas para aferir OCR e segmentação de mãos. Não há validação de sessões completas de 40–60 minutos, análise equity/EV de mãos extraídas nem cortes MP4 explicativos de ponta a ponta.

Próximo ciclo: oferecer uma interface HTML offline para editar/exportar os vereditos sem editar JSON manualmente, com sanitização e verificação no backend; depois vincular somente os campos visualmente revisados ao histórico, sem autorizar matemática antes da validação das mãos.
