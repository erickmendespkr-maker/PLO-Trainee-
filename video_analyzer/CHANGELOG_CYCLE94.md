# PLO Trainee — Ciclo 94 (25/10/2026)

## Escopo e segurança
Somente `feature/plo5-plo6-training`; escopo em `docs/VIDEO_ANALYZER_SCOPE.md`. Ferramenta **offline/assíncrona** para analisar gravações PLO5/PLO6. Sem simulador de mesas, agentes de jogo, captura ao vivo, integrações com plataformas de poker ou apostas.

## Implementação
- Novo `hand_visual_history_bridge.py`: revalida vídeo, navegação, revisão manual, auditoria FFmpeg, galeria de imagens e vereditos humanos finalizados antes de gerar um índice JSON das anotações das mãos com seus respectivos vereditos visuais.
- Cada anotação preserva mesa, intervalo, campo/ação, valor **alegado**, origem, confiança original, timestamp, SHA-256 do PNG auditado (quando existente), veredito, revisor, justificativa e confiança visual subjetiva.
- `confirmed_visual` significa **somente** que uma pessoa revisou uma imagem associada ao timestamp; não comprova a reconstrução integral da mão nem a correção de cartas/ações, equity, EV ou erro estratégico.
- `pending`, `uncertain`, `rejected_visual`, `unreviewable` e hipóteses permanecem explícitos. Todas as flags de autoridade matemática/seleção automática permanecem `false`.
- O relatório de vereditos precisa corresponder exatamente ao resultado do comando `finalize`; são rejeitados hashes, identidades, contagens e permissões forjadas. Saída nova, fora das pastas de evidências, sem sobrescrever entradas.

## Exemplo de execução
```bash
cd video_analyzer
python hand_visual_history_bridge.py VIDEO.mp4 navigation.json review.json stills/ gallery/ visual_verdicts.json history_with_visual_verdicts.json --regions-json regions.json
```

## Verificações executadas localmente
- `python -m unittest -q test_hand_visual_history_bridge`: **13 testes aprovados** com fixtures sintéticas de quatro mesas.
- `python -m unittest -q test_hand_visual_history_bridge test_hand_action_review_form test_hand_action_visual_verdicts test_hand_action_review_gallery test_hand_action_pts_evidence test_boundary_hand_draft test_boundary_history_bridge`: **93 testes selecionados aprovados**, incluindo os 13 novos. Isso não representa a suíte completa.
- Demonstração sintética do ciclo 93 processada pelo novo módulo: **4 intervalos**, **24 anotações**, **7 pendentes**, **1 incerta**, **16 não revisáveis**, sem conclusões matemáticas. Nenhum vídeo real analisado.

## Limitações e bloqueios
- A validação reproduz os relatórios e hashes dos PNGs, mas não mede a exatidão do conteúdo visual nem comprova a mão completa.
- Falta vídeo autorizado de 3–5 minutos e anotações humanas de referência. Não estão validados OCR real, gravações de 40–60 minutos, nem pipeline completo equity/EV → seleção de mãos → clipes MP4.
- Suíte completa e CI remoto não verificados neste ciclo.

## Próximo ciclo
Preparar entrada conservadora para cenários matemáticos com origem e hipóteses explícitas, bloqueando decisões baseadas apenas em vereditos visuais e testando os limites de incerteza. Também avaliar uso em navegador real quando disponível.
