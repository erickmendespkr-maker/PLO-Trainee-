# Ciclo 100 — handoff offline de evidências para revisão humana (25/10/2026)

Escopo: `docs/VIDEO_ANALYZER_SCOPE.md`. Publicar exclusivamente na branch `feature/plo5-plo6-training`.

## Implementado

- `offline_job_review_handoff.py`: integra a auditoria somente leitura de `offline_job_evidence_audit.py` aos quadros extraídos pelo worker, associando candidatos OCR **não verificados** à mesa, imagem e timestamp nominal auditados.
- Exige estado `review_required` e rejeita saltos no índice das imagens, timestamps nominais inconsistentes, OCR fora da mesa/quadro, divergência de contagens, modelos de revisão já aprovados, índices incorretos e arquivos adulterados quando o manifesto inclui SHA-256 por imagem.
- Gera `review_handoff/review_handoff.json` e galeria estática `review_handoff/index.html` na pasta do job, sem sobrescrever saídas e sem modificar SQLite. Até 120 imagens aparecem na galeria; o índice JSON mantém todas as referências auditadas.
- Mantém `hand_reconstruction_verified`, `ready_for_equity_or_ev` e `automatic_clip_selection_authorized` como `false`. Não há captura ao vivo, simulador, adversários de IA ou conexão com plataformas de pôquer.
- Quando o manifesto não contém hashes de quadros (versão atual do sampler na branch), o relatório declara `manifest_frame_hashes_matched=false`. Hashes computados após a extração **não** comprovam autenticidade original.

## FEITO E TESTADO (local)

- `python -m unittest -v test_offline_job_review_handoff`: **20 testes aprovados**.
- `python -m unittest -v test_offline_job_review_handoff test_offline_job_evidence_audit test_offline_worker test_offline_batch test_offline_jobs`: **63 testes aprovados**.
- `python -m py_compile offline_job_review_handoff.py test_offline_job_review_handoff.py`: aprovado.
- Teste com FFmpeg e Tesseract: vídeo sintético de 3 s, quatro regiões, 12 PNG, três candidatos OCR não verificados, geração de HTML e JSON.
- Teste sintético de **40 minutos**, 320×240, 1 fps, tela preta, quatro regiões e amostragem de 60 s: 160 quadros, worker 0,256 s e handoff 0,007 s neste ambiente. **Não** representa desempenho em gravações reais, resolução real, OCR pesado ou sessões de 60 minutos.
- Ambiente local: snapshot de código do Ciclo 98 complementado pelos arquivos de auditoria do Ciclo 99. A versão do worker no GitHub difere desse snapshot; **não** afirmar regressão remota completa.

## Uso

No diretório `video_analyzer/`, após processamento de um job em `review_required`:

```sh
python offline_job_review_handoff.py /dados/jobs.sqlite JOB_ID /dados/results --export
```

Abrir `/dados/results/JOB_ID/review_handoff/index.html` localmente. O arquivo `review_handoff.json` é um índice de revisão, **não** um histórico de mão confirmado.

## NÃO VERIFICADO / BLOQUEIOS

- Suíte completa e CI remoto não executados. Sem validação em navegador real; HTML inspecionado por testes de geração.
- Sem medição de OCR ou reconstrução de mãos reais; falta vídeo autorizado de 3–5 minutos com anotações humanas.
- Não foi validado um fluxo completo de 40–60 minutos com vídeo real, equity/EV e clipes MP4 a partir de reconhecimento visual.
- Timestamp do sampler permanece nominal, não PTS de origem confirmado; SHA-256 verifica bytes e não semântica visual.

## PRÓXIMO

Validar handoff e galeria em navegador real, integrar revisão humana persistida ao histórico de mãos, testar worker e auditoria com a versão exata da branch, e medir OCR/reconstrução em gravação autorizada. Não liberar equity/EV sem cartas, ações e ranges suficientes e revisão humana.
