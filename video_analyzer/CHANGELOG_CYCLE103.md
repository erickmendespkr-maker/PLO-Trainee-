# PLO Trainee — Ciclo 103: janelas provisórias de revisão OCR (offline)

Escopo: `docs/VIDEO_ANALYZER_SCOPE.md`. Nenhuma mesa jogável, IA adversária, captura em tempo real ou integração com plataformas de pôquer.

## Implementação

- `offline_job_review_windows.py`: agrega observações OCR **por mesa e proximidade temporal nominal** para navegação e revisão humana. Os agrupamentos **não** são mãos identificadas; lacunas de amostragem não provam começo/fim de mão.
- Reusa `timeline_job`, que reaudita a gravação, as evidências e a revisão humana antes de criar as janelas. Não utiliza o arquivo de timeline persistido como fonte de verdade.
- Parâmetros `--gap-seconds` (padrão 15; máximo 120) e `--max-span-seconds` (padrão 120; máximo 600). Até quatro mesas e 20.000 observações, com limites para timestamps, caminhos de imagem, hashes, valores revisados e saída.
- Cada janela registra mesa, primeiro/último timestamp nominal, referências às imagens e hashes, contagem de estados, chaves de observação e indicação de revisão pendente. `hand_start_or_end_verified=false` e `ready_for_equity_or_ev=false` sempre.
- Exportação opcional `--export` em `human_ocr_review_windows.json`, escrita única sem sobrescrita, recusando diretório de job simbólico.
- `test_offline_job_review_windows.py`: 24 testes sintéticos, incluindo agrupamento de quatro mesas, limites temporais, rejeição de adulterações, reauditoria de fixture real do pipeline e bloqueio após adulteração de imagem.

## Uso

```bash
python video_analyzer/offline_job_review_windows.py jobs.sqlite <job_id> results/
python video_analyzer/offline_job_review_windows.py jobs.sqlite <job_id> results/ --gap-seconds 15 --max-span-seconds 120 --export
```

Requer job processado e relatório de revisão humana `results/<job_id>/human_ocr_review.json` previamente exportado e válido. A saída não libera equity, EV, priorização automática ou clipes.

## Verificações locais

- `python -m unittest -q test_offline_job_review_windows`: **24 testes aprovados**.
- Seleção de regressão OCR, jobs, FFmpeg/segmentação, ranges/EV e exportação MP4: **196 testes aprovados** (inclui os 24 novos).
- `python -m py_compile offline_job_review_windows.py test_offline_job_review_windows.py`: aprovado.
- Ambiente: snapshot local do Ciclo 98 + módulos 99–102; `offline_jobs.py` local difere do blob da branch GitHub. Regressão da árvore exata da branch e CI remoto não verificados.

## Limitações e bloqueios

- A janela é um índice temporal de OCR; **não** identifica mãos, cartas corretas, ações ou PTS exatos. Agrupar observações próximas pode unir mãos diferentes ou dividir a mesma mão.
- SHA-256 vincula os dados auditados no momento da leitura, não autentica identidade do revisor nem prova interpretação correta.
- Falta vídeo real autorizado de 3–5 minutos com anotações para medir precisão e validar o fluxo de ponta a ponta.
