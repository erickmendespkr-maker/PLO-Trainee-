# PLO Trainee — Ciclo 104: intervalos nominais marcados por humanos

Escopo: `docs/VIDEO_ANALYZER_SCOPE.md`; somente vídeos gravados, processamento offline/assíncrono e revisão humana. Nenhuma mesa jogável, captura ao vivo ou integração com sites de pôquer.

## Implementação

- `offline_job_hand_interval_review.py` produz **template vazio** a partir de uma timeline OCR revalidada; não transforma automaticamente uma janela temporal em mão.
- O revisor informa intervalos **nominais**, rótulos de mãos e confiança **subjetiva**; o módulo associa somente as observações OCR existentes nos intervalos, por mesa. Um mesmo intervalo pode cruzar janelas de navegação, e uma janela pode ser dividida em vários intervalos humanos.
- Cada submissão fica vinculada ao hash SHA-256 das janelas recalculadas; `review_job` reaudita vídeo, imagens e relatório de OCR via `timeline_job` antes de aceitar os dados.
- Valida esquema exato, rótulos, limites, intervalos sem sobreposição, números finitos, confiança e referências. Limites: quatro mesas, até 2.000 intervalos, até 600 segundos por intervalo e 20.000 observações OCR do módulo anterior.
- Exportação JSON exclusiva, sem sobrescrita, com verificação de diretório simbólico e tamanho máximo de 4 MiB. Nenhuma mudança no banco, gravação ou evidências.
- `hand_start_or_end_pts_verified=false`, `hand_reconstruction_verified=false`, `ready_for_equity_or_ev=false` e `automatic_clip_selection_authorized=false` permanecem explícitos em toda saída. Os timestamps de amostragem **não** são PTS exatos.

## Uso

```bash
# Produzir template JSON a partir do job auditado:
python video_analyzer/offline_job_hand_interval_review.py jobs.sqlite <job_id> results/ > hand_intervals_submission.json

# Após preenchimento manual de reviewer e intervals, validar sem exportar:
python video_analyzer/offline_job_hand_interval_review.py jobs.sqlite <job_id> results/ --submission hand_intervals_submission.json

# Exportar uma única vez, sem sobrescrever:
python video_analyzer/offline_job_hand_interval_review.py jobs.sqlite <job_id> results/ --submission hand_intervals_submission.json --export
```

Campos de um intervalo: `table_id`, `hand_label`, `start_nominal_seconds`, `end_nominal_seconds`, `reviewer_confidence_subjective`, `reviewer_notes`. O revisor deve assistir ao vídeo antes de preenchê-los. A exportação não é um histórico completo da mão.

## Testes locais

- `python -m unittest -q test_offline_job_hand_interval_review test_offline_job_review_windows test_offline_job_review_timeline`: **72 testes aprovados** (27 novos).
- Seleção ampliada incluindo OCR, jobs, FFmpeg/worker, cenários matemáticos e exportação de clipes: **223 testes aprovados**, incluindo os 27 novos.
- Módulos centrais `offline_job_review_windows.py`, `offline_job_review_timeline.py`, `offline_job_review_handoff.py`, `offline_job_evidence_audit.py` e os testes correspondentes comparados com hashes Git da branch. Alguns módulos legados locais, inclusive `offline_jobs.py`, `offline_worker.py` e `offline_batch.py`, diferem da branch; **não** é uma regressão integral da árvore exata do GitHub.
- Testes sintéticos; sem vídeo autorizado real e sem validação de reconstrução visual ou cálculos end-to-end.

## Bloqueios

- A marcação humana de intervalos nominais não prova começo/fim real de uma mão. Lacunas podem esconder ações ou mãos inteiras. Não inferir cartas escondidas.
- Falta vídeo PLO5/PLO6 autorizado de 3–5 minutos com anotações para calibrar OCR e medir precisão.
- A validação com a árvore completa exata da branch, o CI remoto e o fluxo completo vídeo → análise matemática → cortes MP4 ainda precisam de verificação.
