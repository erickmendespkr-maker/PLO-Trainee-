# Finalização F4 — pacote unificado de revisão offline PLO5

## Entrega
plo5_review_pipeline.py reúne extração opcional de janelas densas, auditoria independente de cada janela, OCR de pote/stack com leitor compartilhado entre janelas, fusão de candidatos, cópia integral dos prints, relatório HTML filtrável por mesa e relatório estratégico opcional separado. Registra tempo por etapa e estatísticas de cache. A saída só é publicada após rechecagem dos vínculos e hashes. Preserva as rotas antigas; não renderiza MP4.

Uso:
    python video_analyzer/plo5_review_pipeline.py JOB_JSON WINDOWS_JSON OUTPUT_DIR --workers 2 --capacity 512

JOB_JSON: objeto database, job_id, annotations. WINDOWS_JSON: lista de caminhos para timeline.json em pastas window_NN, do mesmo job. Com --extract, WINDOWS_JSON é uma lista de objetos job_id, start, seconds, conforme plo5_dense_timeline. Limite atual: 8 janelas e 512 recortes. Exige job pré-ingestado e calibração válida. --study aponta a JSON com drafts e study_input; --mode quick/deep afeta somente o relatório estratégico opcional. Não faz associação automática entre decisões esparsas e candidatos densos. --capacity 0 desativa reutilização.

Pacote: index.html, prints/, review.json, money.json, manifest.json, dense/ quando extraído e study/ quando fornecido. Em modo de extração os prints são duplicados no pacote para manter evidência e portabilidade. A leitura financeira contém candidatos de valores, não ledger ou confirmação de ganhos/perdas.

## Validação
Linux Python 3.13.5: 24 testes aprovados (7 novos e 17 regressões F2), 0,060 s. Os novos testes executam escrita real de PNG/HTML/JSON e checagem de hashes, mas simulam auditoria de mídia, OCR e camada estratégica; não são teste ponta a ponta com vídeo. Dois blobs publicados conferidos com git hash-object local.
Benchmark de cinco repetições, 480 PNGs sintéticos 402x748, quatro mesas, duas janelas de 60 segundos, fusão + cópia + HTML: mediana 0,054180329 s, 1.211.040 bytes de prints, 4 segmentos, 480 hashes de saída conferidos em cada repetição, zero MP4. Exclui OCR, extração e análise estratégica. Não representa tempo de uma sessão real.

## Pendências
F4 parcial: execução real da integração, conexão automática das decisões ao histórico reconstruído, captura de ações e posições, ledger, fontes GTO, banco original e benchmark integral de sessão de uma hora ainda pendentes. Não foi realizado checkout integral nem validação Windows. Preservar F1–F3 e pendências originais. Próximo disparo planejado F5; não criar novos blocos. Sem alterações em main, deploy ou automação.
