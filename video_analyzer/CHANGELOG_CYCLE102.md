# PLO Trainee — Ciclo 102: timeline auditável de revisão OCR (offline)

Escopo: `docs/VIDEO_ANALYZER_SCOPE.md`. Nenhuma mesa jogável, IA adversária, captura ao vivo ou integração com pôquer real.

## Implementado

- `offline_job_review_timeline.py`: constrói uma **timeline de candidatos OCR** a partir do relatório `human_ocr_review.json` do Ciclo 101 e de um handoff **reconstruído a partir da gravação e das evidências**. Revalida a estrutura completa do relatório por `validate_submission`, incluindo índices, timestamps, revisão humana e vínculo com OCR original. Recusa chaves extras, divergências e fontes alteradas.
- Associa cada observação à mesa (1–4), timestamp **nominal**, imagem auditada e SHA-256, campo OCR, candidato original, veredito humano, valor anotado (quando confirmado/corrigido), confiança subjetiva e justificativa. Candidatos não revisados permanecem `pending`, sem valor aprovado.
- Saída JSON com contagens, hashes e bloqueios explícitos: `hand_reconstruction_verified=false`, `ready_for_equity_or_ev=false`, `automatic_clip_selection_authorized=false`.
- `--export` grava `human_ocr_timeline.json` uma única vez (`O_EXCL`), sem sobrescrever dados, editar fila, tocar `main`, enviar dados à rede ou iniciar cálculos.
- `test_offline_job_review_timeline.py`: testes sintéticos de quatro mesas, decisões parciais/completas, alterações no OCR e no relatório, caminhos e hashes de imagens, symlinks, JSON duplicado, contagens, idempotência, auditoria de fixture real e adulteração de imagem.

## Uso

```bash
# Após concluir o job, gerar o handoff e exportar a revisão humana do Ciclo 101:
python video_analyzer/offline_job_review_timeline.py jobs.sqlite <job_id> results/
# Apenas se a prévia validada estiver correta:
python video_analyzer/offline_job_review_timeline.py jobs.sqlite <job_id> results/ --export
# Saída: results/<job_id>/human_ocr_timeline.json
```

## Testes locais deste ciclo

- `python -m unittest -q test_offline_job_review_timeline`: **21 aprovados**.
- `python -m unittest -q test_offline_job_review_timeline test_offline_job_review_decisions test_offline_job_review_editor test_offline_job_review_handoff test_offline_job_evidence_audit`: **90 aprovados** (inclui os 21 novos).
- `python -m py_compile .../offline_job_review_timeline.py`: aprovado.
- Execução ampliada `python -m unittest discover -p 'test_*.py' -q`: **interrompida por timeout**, sem resultado conclusivo.
- Os testes usaram snapshot local do Ciclo 98 mais os módulos 99–101. Os arquivos `offline_job_review_timeline.py`, `offline_job_review_decisions.py` e `offline_job_review_handoff.py` usados no teste correspondem aos publicados; `offline_jobs.py` local difere do blob da branch remota. Regressão exata de toda a branch permanece pendente.

## Limitações

- Isto **não** reconstrói mãos nem transforma OCR em verdade factual. Não realiza equity, EV ou cortes automáticos.
- Os timestamps são posições **nominais de amostragem**, não PTS originais comprovados.
- SHA-256 permite detectar inconsistências entre os arquivos revalidados, mas não prova a correção da leitura das cartas. Quando o manifesto não fixa hashes de imagens, não existe baseline independente.
- Não há autenticação criptográfica do revisor: alguém com permissão para editar o relatório pode alterar justificativas ou valores humanos *válidos*; o verificador garante consistência com OCR e evidências, não autoria.
- Não foi fornecido vídeo real autorizado para medir precisão do OCR e segmentação de mãos. Os testes usam somente dados sintéticos.

## Próximo ciclo

Validar a integração com um checkout exato da branch remota, construir ferramenta de agrupamento **provisório** por mesa e intervalo (sem promover observações a mãos confirmadas) e, após receber vídeo autorizado de 3–5 minutos, medir reconhecimento e reconstrução contra gabarito humano.
