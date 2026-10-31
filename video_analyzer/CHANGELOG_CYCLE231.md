# Ciclo 231 — Importação independente de revisão visual

## Escopo
Continuidade do pipeline **offline e assíncrono** de vídeos gravados PLO5/PLO6, sem mesas jogáveis, integrações com pôquer ao vivo ou execução de apostas.

## Entrega
- Novo módulo offline_visual_evidence_review_import.py consome o JSON exportado pela interface visual.
- Reconstrói o pacote de evidências a partir do OCR, reconstrução, ledger de revisão e quadros PNG; não confia em campos imutáveis do JSON recebido.
- Verifica identidade da mão/mesa/campo/slot, valor declarado, índice da observação, timestamp, SHA-256, ordenação, quantidade de registros e sinalizadores de segurança.
- Rejeita alterações de evidências, dados de origem, campos extras, entradas duplicadas ou removidas, notas inválidas, estados desconhecidos, arquivos alterados e tentativa de marcar como visível um campo sem imagem associada.
- Revalida todos os quadros no fim da importação, além das verificações realizadas pelo módulo de auditoria.
- Preserva apenas três estados: uncertain, not_visible, seen_by_reviewer; a terceira opção é **declaração humana não autenticada**.
- O ledger de saída permanece eligible_for_equity: 0 e equity_or_ev_calculated: false; nenhuma carta, ação ou mão é promovida a verdade visual ou entrada matemática.

## Testes locais realizados
- 23 testes específicos do importador: aprovados.
- 213 testes selecionados de importação, interface, auditoria, reconstrução e módulos adjacentes: aprovados.
- Testes com dados sintéticos; não medem acurácia OCR nem demonstram processamento de vídeos reais.
- Não foram usados GitHub Actions, serviços de produção ou recursos pagos.

## Exemplo de uso
Com o diretório video_analyzer disponível no PYTHONPATH:

    python video_analyzer/offline_visual_evidence_review_import.py ocr.json reconstruction.json reviewed.json frames/ visual_review_draft.json visual_review_ledger.json

A saída deve ser um arquivo JSON novo, não existente.

## Bloqueios
Ainda falta um vídeo autorizado e anotado de 3–5 minutos para validar a precisão de detecção de mesas, cartas, ações e timestamps. Não foram validadas sessões completas de 40–60 minutos, Windows ou a suíte integral do repositório.

## Próximo passo
Consolidar os registros de revisão visual com estados por mão/street e construir um contrato matemático **separado**, exigindo cartas completas, regras Omaha (duas cartas privadas e três do board), ranges, parâmetros de simulação, hipóteses e incerteza explícitos. Não inferir verdade visual a partir da simples confirmação humana.
