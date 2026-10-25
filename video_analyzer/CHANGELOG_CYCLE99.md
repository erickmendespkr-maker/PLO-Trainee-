# Ciclo 99 — auditoria de evidências de jobs offline (25/10/2026)

Escopo: `docs/VIDEO_ANALYZER_SCOPE.md`. Branch exclusiva `feature/plo5-plo6-training`.

## Implementado

- `offline_job_evidence_audit.py`: auditoria **somente leitura** do estado `review_required` produzido por `offline_worker.py` e armazenado por `OfflineJobStore`.
- Confere o SHA-256 da gravação original, metadados, resultado do worker, manifesto e imagens PNG. Vincula o pacote ao `job_id`, à região de mesa e aos timestamps **nominais** de amostragem.
- Recusa IDs inválidos, referências a outras mesas, contagens inconsistentes, arquivos ausentes, imagens repetidas, caminhos fora da pasta do job, symlinks, arquivos excessivos, JSON não finito e resultados que tentam evitar revisão humana.
- Emite JSON com SHA-256 de cada imagem e totais por mesa, sem transformar OCR ou quadros em cartas/ações verificadas. `hand_reconstruction_verified`, `ready_for_equity_or_ev` e `automatic_clip_selection_authorized` são sempre `false`.
- CLI aceita `--output` somente para arquivo novo (`open('x')`), sem alterar fila, gravações ou arquivos anteriores.

## FEITO E TESTADO

- `python -m unittest -v test_offline_job_evidence_audit`: **19 testes aprovados**.
- `python -m py_compile offline_job_evidence_audit.py test_offline_job_evidence_audit.py`: aprovado.
- Um dos testes gera vídeo MP4 artificial de 2 segundos via FFmpeg, extrai 4 PNG de regiões de mesas e verifica hashes e contagens. Nenhuma imagem contém pôquer real.
- Os arquivos publicados foram comparados por Git blob SHA com os arquivos locais testados.

## Uso (no diretório video_analyzer)

```sh
python offline_job_evidence_audit.py /dados/jobs.sqlite JOB_ID /dados/results --output /dados/audit_novo.json
```

A fila já deve ter processado o job, produzindo `results/JOB_ID/result.json`, `manifest.json` e PNGs. Sem `--output`, o relatório é impresso em stdout. O JSON é uma **auditoria de integridade de bytes**, não certificação de leitura visual.

## NÃO VERIFICADO

- Não foi executada a suíte completa nem CI remoto; testes do módulo são sintéticos/isolados, com uma prova real de FFmpeg.
- Ainda não existe validação de reconhecimento real de cartas, ações, OCR ou reconstrução de mãos a partir de uma gravação autorizada.
- Ainda não foi validado um fluxo ponta a ponta de 40–60 minutos, nem o processamento automático até equity/EV e cortes MP4.
- O teste de PNG verifica assinatura e hash, não a decodificação independente nem PTS de origem. O worker ainda utiliza grade temporal nominal.

## PENDÊNCIAS

Gravação autorizada PLO5/PLO6 de 3–5 minutos, com anotações humanas de referência, para aferir a reconstrução. Sem credenciais ou gastos.

## PRÓXIMO CICLO

Integrar a auditoria ao handoff de revisão humana, medir tempos/memória em vídeos longos sintéticos e, com gravação real autorizada, medir precisão de OCR e identificação de mãos. Não liberar cálculos sem revisão e ranges explícitos.
