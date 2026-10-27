# Ciclo 136 — Exportação offline de clipes com explicação

Escopo: `docs/VIDEO_ANALYZER_SCOPE.md`; **somente análise de gravações**. Sem simulador, mesas jogáveis, adversários de IA ou integração com plataformas de pôquer.

## Novo componente

`offline_reviewed_math_clip_export.py` exporta um MP4 com trilha de legendas `mov_text` (português), arquivo SRT e relatório JSON para **uma janela temporal aprovada explicitamente** por revisão humana. Usa FFmpeg/FFprobe e H.264; mantém áudio quando existente.

Entrada: vídeo MP4/WebM local, relatório de handoff do ciclo 135, candidato exato enviado ao bridge Monte Carlo do ciclo 134, relatório matemático do bridge e anotação manual dos tempos. Verifica hash SHA-256 real do arquivo de vídeo, vínculo por hash dos bytes exatos do candidato com o relatório matemático, mesa/mão/variante, range declarado, semente, trials, contagem de vitórias/empates/derrotas, coerência da fórmula de EV, consentimento para exportar e limites temporais. Saídas usam links rígidos exclusivos, evitando sobrescrita; falhas limpam arquivos publicados parcialmente.

**Não** reconhece cartas nem ações no vídeo; o timestamp é informado por humano. A declaração `monte_carlo_recomputed` e a confiabilidade do range continuam dependentes do relatório matemático recebido, sem recomputação neste componente. A CI Hoeffding reflete apenas erro amostral de Monte Carlo. O vídeo sintético demonstra exportação técnica, não análise de poker real.

## Comando

```bash
python video_analyzer/offline_reviewed_math_clip_export.py \
  sessao.mp4 handoff.json candidato_bridge.json resultado_monte_carlo.json \
  anotacao_manual_clipe.json saidas/mao42
```

A anotação exige `schema_version`, `source_kind`, `table_id`, `hand_label`, `reviewer_label`, `start_seconds`, `decision_seconds`, `end_seconds`, `approved_for_export=true` e `notes`. Janela permitida: 1–180 s, dentro da duração verificada por FFprobe.

## Testes e limitações

- 19 testes sintéticos do novo módulo, incluindo geração real de MP4/legendas com FFmpeg, hashes, não sobrescrita, adulteração de relatório e rejeição de timestamps inválidos.
- 52 testes de regressão dos ciclos 135 e 133 (71 selecionados no total) aprovados localmente.
- Não executada suíte completa; não validado vídeo real autorizado de 3–5 minutos; não validado OCR nem pipeline de sessões de 40–60 minutos.
- A geração de um clipe **não prova** que a ação, cartas ou a estimativa matemática correspondem ao conteúdo visual.