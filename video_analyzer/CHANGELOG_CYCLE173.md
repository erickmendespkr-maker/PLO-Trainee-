# Ciclo 173 — revisão humana de campos OCR

Escopo: somente gravações offline autorizadas de PLO5/PLO6, conforme docs/VIDEO_ANALYZER_SCOPE.md. Nenhuma integração ao vivo, mesa jogável ou aposta.

## Implementação
- offline_roi_human_review.py recebe o diretório de propostas OCR do Ciclo 172, anotações humanas JSON e um novo diretório de saída.
- As anotações ficam vinculadas ao SHA-256 do relatório OCR e ao SHA-256 de cada PNG. Preserva timestamps decodificados, mesa, campo e referência à imagem original.
- Estados: confirmed, corrected, rejected, inconclusive e pending. Confirmações exigem texto OCR e valor normalizado informado explicitamente; correções exigem justificativa; rejeições e inconclusões não podem conter valor.
- Valida números de fichas, cartas e ações; não compara a revisão com a imagem nem comprova consistência entre campos de uma mão.
- Recusa JSON com chaves duplicadas, valores não finitos, symlinks, PNGs adulterados, identidades repetidas e diretório de saída preexistente.
- Publica o resultado em novo diretório sem sobrescrever evidências. Mesmo após revisão humana, ready_for_equity_or_ev=false e hands_reconstructed=false.

## Reprodução
Python 3.11+ no diretório video_analyzer:

    python -m unittest -v test_offline_roi_human_review
    python offline_roi_human_review.py OCR_OUTPUT_DIR ANNOTATIONS_JSON NEW_OUTPUT_DIR

Formato das anotações: objeto com schema_version=1, source_roi_ocr_report_sha256 e reviews. Cada review tem proposal_index, source_roi_png_sha256, decision, normalized_value (texto ou null) e note.

## FEITO E TESTADO
- 23 testes novos de revisão, validação, integridade e preservação de fontes aprovados.
- 92/92 testes passaram no Linux ao executar os 23 novos com 69 testes dos ciclos 168–172 (usando o pacote local do Ciclo 172). FFmpeg e Tesseract exercitados pelos testes anteriores.
- Demonstração com três propostas OCR sintéticas do Ciclo 172: uma confirmada, uma inconclusiva, uma rejeitada; JSON consolidado produzido e EV bloqueado.
- Testes locais, sem GitHub Actions.

## NÃO VERIFICADO
- Nenhuma revisão humana real, gravação real, teste Windows ou processamento de sessão real de 40–60 minutos.
- Não executada a suíte completa do repositório.
- Não detecta limites de mãos, não reconstrói sequências de ações, não calcula equity/EV e não cria interface gráfica.
- Continua faltando vídeo autorizado e anotado de 3–5 minutos para medir precisão.

## PRÓXIMO CICLO
Conectar campos revisados a rascunhos de histórico de mãos com validação cruzada de cartas, timestamps e ausências, mantendo bloqueios de equity/EV. Preparar interface local de revisão visual.
