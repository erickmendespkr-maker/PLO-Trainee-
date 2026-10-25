# PLO Trainee — Ciclo 101: revisão humana offline de candidatos OCR

Escopo: `docs/VIDEO_ANALYZER_SCOPE.md`. Não existe captura ao vivo, mesa jogável, adversário artificial ou integração com sites de pôquer.

## Novos componentes

- `offline_job_review_editor.py`: formulário HTML **local**, sem chamadas de rede, criado a partir de um `build_handoff` recém-auditado. Permite revisar candidatos OCR em páginas de 30 itens, corrigir/confirmar/rejeitar/registrar incerteza, justificar, atribuir confiança subjetiva e baixar JSON.
- `offline_job_review_decisions.py`: reaudita o vídeo e as evidências na importação; valida esquema estrito, fingerprint SHA-256 do handoff completo, mesa, timestamp nominal, índice e campo OCR. Rejeita alterações, duplicações, confiança inválida, JSON com chaves duplicadas, valores não finitos e arquivos de entrada simbólicos. Exporta JSON uma única vez, sem sobrescrever.
- `test_offline_job_review_editor.py` e `test_offline_job_review_decisions.py`: testes sintéticos, incluindo um handoff real da fixture anterior, validação de JavaScript com Node, proteção contra injeção HTML, e bloqueio de análises matemáticas.

## Uso local (após concluir um job e gerar review_handoff)

```bash
python video_analyzer/offline_job_review_editor.py jobs.sqlite <job_id> results/
# Abra results/<job_id>/review_handoff/ocr_review_editor.html
# Selecione decisões explícitas e exporte o arquivo JSON pelo navegador.
python video_analyzer/offline_job_review_decisions.py jobs.sqlite <job_id> results/ ocr_review_submission.json
python video_analyzer/offline_job_review_decisions.py jobs.sqlite <job_id> results/ ocr_review_submission.json --export
```

A primeira chamada do validador faz uma verificação sem escrita. `--export` grava `human_ocr_review.json` uma única vez. A origem do vídeo e as imagens são novamente auditadas; a fila não é alterada. Não há consumo de API externa nem custos de hospedagem.

## Limites deliberados

- **Nenhum** OCR é automaticamente aceito como fato. `confirmed`/`corrected` são *anotações humanas*, não reconstrução de mão.
- Mesmo com todos os candidatos OCR revisados, `ready_for_equity_or_ev` e `automatic_clip_selection_authorized` permanecem `false`; a revisão de cartas, ações, ranges, pot e contexto ainda é necessária.
- Timestamps continuam **nominais**. SHA-256 comprova consistência dos bytes com a auditoria corrente, não a verdade das cartas; quando o manifesto original não fixa os hashes dos quadros, não existe uma linha de base independente para cada imagem.
- O editor suporta até 3000 candidatos por página HTML (30 por página de navegação). O importador JSON aceita até 20 mil decisões e 2 MB de entrada.
- Não há vídeo real de referência autorizado; OCR e reconstrução não possuem precisão mensurada.
- Testes locais usam componentes de um snapshot anterior, complementado pelos módulos dos Ciclos 99/100. Os arquivos `offline_worker.py` e `offline_jobs.py` desse snapshot diferem dos blobs publicados na branch atual. A regressão com **todos** os componentes remotos atuais ainda não foi executada.

## Próximo marco

Executar regressão com checkout exato da branch e, após receber vídeo autorizado de 3–5 minutos, medir OCR, segmentação de mãos e confiança por campo contra anotação humana. Em seguida, ligar apenas mãos completamente revisadas ao motor Monte Carlo e aos cortes MP4, com hipótese e proveniência explícitas.
