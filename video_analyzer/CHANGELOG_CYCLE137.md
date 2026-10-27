# Ciclo 137 — Orquestração offline de revisão, Monte Carlo e cortes MP4

Escopo: `docs/VIDEO_ANALYZER_SCOPE.md`. Somente vídeos gravados; não existe integração com clientes de poker, mesas jogáveis, adversários artificiais ou decisões em tempo real.

## Implementação

Novo `offline_reviewed_pipeline.py`: coordena os módulos existentes `offline_review_queue_math_handoff`, `offline_reviewed_range_equity_bridge` e `offline_reviewed_math_clip_export`. Recebe vídeo local, revisão de uma mão, anotação manual de tempos e diretório novo de saída. Não identifica automaticamente cartas, mãos ou timestamps.

Fluxo: snapshot dos dois JSONs de entrada (sem seguir symlinks) -> handoff de revisão -> bridge de equity Monte Carlo e EV condicional -> exportação FFmpeg de MP4/SRT/JSON com legenda e aprovação explícita -> manifesto de integridade. Se a revisão estiver pendente, publica apenas um relatório `blocked_review`, sem candidato, equity ou vídeo. Se o cálculo for bloqueado, publica `blocked_math`, sem MP4. Em falha de exportação, não publica diretório parcial.

Os arquivos são preparados em diretório temporário no mesmo sistema de arquivos e publicados como hardlinks exclusivos em um diretório novo. `pipeline.json` registra SHA-256 e tamanho dos arquivos, identificador da mesa/mão, bloqueios e limitações. Não sobrescreve arquivos existentes.

## Comando

```bash
python video_analyzer/offline_reviewed_pipeline.py \
  gravacao.mp4 entrada_revisao.json anotacao_clipe.json saida_nova
```

`entrada_revisao.json` segue o schema do ciclo 135, e `anotacao_clipe.json` o schema do ciclo 136. O motor matemático exige as dependências originais do repositório. A saída precisa ser um diretório ainda inexistente, em pasta local já existente. Os clipes só são gerados quando o revisor aprovou os tempos e o relatório Monte Carlo não está bloqueado.

## Testes e limitações

- 9 testes smoke publicados no GitHub e executados localmente: geração **real** de MP4 com FFmpeg e legenda `mov_text`, hashes, revisão bloqueada, aprovação ausente, vídeo adulterado, diretório preexistente, symlink, falha de exportação e PLO6 na mesa 4.
- 19 testes adicionais locais do orquestrador, incluindo rollback da publicação, CLI e integridade dos relatórios.
- 71 testes de regressão locais dos módulos de handoff, call EV e exportação MP4.
- **99 testes selecionados aprovados localmente**. Não é a suíte completa.
- Os testes de MP4 usam um **stub que fabrica o relatório matemático** para exercitar a integração de arquivos. Portanto, o motor Monte Carlo original **não foi executado ponta a ponta** neste ciclo. Não confundir o campo `monte_carlo_recomputed` do stub com evidência de execução real.
- Não há vídeo real autorizado; OCR, reconstrução de mãos, precisão estratégica e desempenho de sessões de 40–60 minutos permanecem não verificados.
- Mesmo na execução real, ranges, cartas e tempos continuam hipóteses/declarações de revisão, não observações certificadas.
