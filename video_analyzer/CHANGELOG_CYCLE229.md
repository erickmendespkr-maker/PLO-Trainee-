# Ciclo 229 — auditoria de vínculo de quadros (offline)

Escopo preservado: `docs/VIDEO_ANALYZER_SCOPE.md`. Não existe simulador, acesso a mesa real, captura ao vivo ou cálculo automático a partir de OCR.

## Entregue

- `offline_hand_frame_evidence_audit.py`: correlaciona a declaração de revisão por mão/street com observações OCR previamente aceitas e quadros PNG existentes; exige mesmo `hand_id`, `table_id`, campo, slot, valor, SHA-256 e timestamps a no máximo 0,25 s.
- Verifica integridade do manifesto e dos PNGs, cadeia de hashes dos ledgers, reconstrução reproduzida do OCR e, opcionalmente, hash do vídeo MP4/WebM original.
- Correções manuais ou declarações sem correspondência permanecem `manual_or_unmatched_claim_requires_visual_review`.
- Mesmo quando existe vínculo, o status é `frame_bytes_and_ocr_claim_linked_not_visual_truth`: um hash comprova os bytes, não a carta ou ação exibida.
- Não cria anotações matemáticas; `eligible_for_equity=0`, `math_ready=false`, `equity_or_ev_calculated=false`.

## Testes locais

- 19 novos testes sintéticos; 164/164 testes selecionados aprovados (19 novos + 145 de regressão).
- Cenários: hashes alterados, timestamps divergentes, quadros adulterados, links simbólicos, correção manual, OCR não aceito, JSON duplicado/NaN, arquivo de saída existente e vídeo com SHA incorreto.
- Testes executados com Python `unittest`, sem GitHub Actions.

## Limitações

- **Sem validação semântica**: a auditoria não determina se a carta realmente está visível na imagem. A declaração do revisor continua não autenticada.
- Não foi executado reconhecimento em vídeo real nem validação de uma sessão de 40–60 min, Windows ou a suíte integral do repositório.
- O relatório de revisão é tratado como não confiável; não há promoção de dados para Monte Carlo ou EV.
- Vídeo real autorizado e anotado de 3–5 minutos ainda não foi fornecido.

## Próximo

Criar uma etapa de revisão humana com evidências visuais por campo, street e timestamp e critérios explícitos para aceitar ou manter incompletas as mãos. Depois integrar a fila matemática com entradas completas, ranges e incertezas, mantendo os casos ambíguos bloqueados.
