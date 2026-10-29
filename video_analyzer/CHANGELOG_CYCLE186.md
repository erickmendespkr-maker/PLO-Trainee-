# Ciclo 186 — triagem OCR vinculada a clipe MP4 revisado (29/10/2026)

Escopo: exclusivamente análise offline/assíncrona de gravações PLO5/PLO6, conforme docs/VIDEO_ANALYZER_SCOPE.md. Sem integração com poker real, decisões ao vivo, mesas jogáveis ou adversários de IA.

## Implementação

Novo módulo video_analyzer/offline_triage_reviewed_clip_pipeline.py conecta a fila determinística offline_action_review_triage.py ao exportador manual offline_reviewed_clip_pipeline.py. Entrada: vídeo, rascunhos, revisão humana de limites, crop, timeline, fila OCR, ID de mão, índice de observação e diretório de saída novo.

Uso:
    python video_analyzer/offline_triage_reviewed_clip_pipeline.py VIDEO.mp4 DRAFTS.json BOUNDARY_REVIEW.json CROP.json TIMELINE.json TRIAGE.json HAND_ID PROPOSAL_INDEX NOVO_DIRETORIO

Valida a fila completa reconstruída da timeline, hashes SHA-256, identidade de mesa/mão/variante, limites originais e revisados, presença do timestamp da ação dentro do corte, crop e integridade do MP4. Usa diretório temporário e publicação atômica. Gera clip.mp4, clip.mp4.json, gate/request.json, gate/provenance.json, manifest.json e triage_clip_link.json.

A revisão humana autoriza somente o intervalo temporal, NÃO valida a ação de poker. Os campos actor_identified, action_legality_verified, ready_for_equity_or_ev, automatic_clip_selection_authorized e source_video_matches_ocr_source_verified permanecem false.

## Testes locais

20 testes novos aprovados, incluindo duas exportações MP4 sintéticas de 9 segundos e rejeições de adulteração de fila, prioridade, autorização, origem, JSON inválido, crop, vídeo, revisão pendente e ação fora dos limites. Com 46 testes existentes de timeline, triagem e gate: 66/66 aprovados com unittest discover. FFprobe do clipe demonstrativo: 9,000000 segundos, 320x180 pixels; fonte sintética de 640x360 pixels. Não foi utilizado vídeo real.

## Limitações

O corte é da mão inteira, não da janela de prévia da ação. O vínculo criptográfico entre o vídeo e os frames OCR não é provado por este módulo. OCR, ator, sequência legal de apostas, equity, EV, ranges e qualidade estratégica permanecem não verificados. Faltam teste no Windows, gravação anotada autorizada de 3–5 minutos, sessões reais de 40–60 minutos e suíte integral do repositório.

Nenhum GitHub Actions, produção, main, credenciais ou gastos foram utilizados ou alterados. Próxima etapa: exigir auditoria vídeo→frames→OCR no fluxo de clipes, antes de iniciar cálculos de equity/EV em mãos verificadas.
