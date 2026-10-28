# Ciclo 174 — rascunhos estruturados de mãos a partir de OCR revisado

Escopo: exclusivamente análise offline de gravações PLO5/PLO6 conforme `docs/VIDEO_ANALYZER_SCOPE.md`.

## Implementado
- `offline_reviewed_hand_drafts.py` recebe `reviewed_ocr_observations.json` do Ciclo 173, limites manuais de mãos em JSON e diretório novo.
- Vincula os limites ao SHA-256 exato do relatório revisado; preserva SHA do relatório OCR, índices de observações, mesa, PTS e estado de revisão.
- Agrupa por mesa (1–4) e intervalo semiaberto `[start_seconds, end_seconds)`, com PLO5/PLO6 por mão; impede intervalos sobrepostos na mesma mesa.
- Separa campos confirmados/corrigidos dos rejeitados, inconclusivos e pendentes.
- Identifica campos ausentes, cartas privadas incompatíveis com PLO5/PLO6, colisão entre cartas privadas e board, divergências entre observações e intervalos sem observações.
- Não assume que intervalo manual corresponde a mão real. Não infere cartas ocultas nem sequência de apostas; `hands_reconstructed=false` e `ready_for_equity_or_ev=false` sempre.
- Limites de tamanho e validação de JSON, chaves duplicadas, symlinks, timestamps, IDs e valores; saída atômica em diretório novo.

## Reprodução
Python 3.11+:
```
cd video_analyzer
python -m unittest -v test_offline_reviewed_hand_drafts
python offline_reviewed_hand_drafts.py REVIEWED_JSON BOUNDARIES_JSON NEW_OUTPUT_DIR
```
Exemplo de limites manuais:
```
{"schema_version":1,"reviewed_report_sha256":"<sha256 do JSON revisado>",
 "hands":[{"hand_id":"H001","table_id":1,"variant":"PLO5",
 "start_seconds":0,"end_seconds":20,"note":"Limites inseridos manualmente"}]}
```

## FEITO E TESTADO
- 18/18 testes sintéticos locais aprovados, após publicação dos dois arquivos Python.
- Os SHA-1 de blob Git publicados coincidem com os arquivos locais testados.
- Demonstração de integração usando `reviewed_ocr_observations.json` sintético do Ciclo 173: dois intervalos artificiais (mesas 1 e 4), pote confirmado somente na mesa 1 e ação rejeitada na mesa 4; EV bloqueado.

## NÃO VERIFICADO
- Suíte completa do repositório, Windows, precisão em vídeo real, limites automáticos de mãos, equity/EV e clipes MP4.
- A existência de um campo OCR revisado não prova a exatidão do conteúdo visual nem que a mão está reconstruída.

## PENDÊNCIAS
- Vídeo autorizado e anotado de 3–5 minutos para avaliação de precisão de OCR e segmentação.

## PRÓXIMO CICLO
- Interface local para revisão dos limites de mãos e campos, com referências a frames.
- Validação temporal de board por streets, ações e valores em sequência, preservando incerteza e bloqueio matemático.
