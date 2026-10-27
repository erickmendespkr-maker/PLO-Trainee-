# Ciclo 132 — fila de revisão humana e benchmark repetido (somente offline)

Escopo: `docs/VIDEO_ANALYZER_SCOPE.md`. Nenhum simulador jogável, adversário, conexão ao pôquer real, credencial ou gasto.

## Componentes

- `offline_hand_evidence_review_queue.py`: recebe um manifesto com relatórios anteriores de ledger, vínculos de crops e auditoria temporal opcional. Confere identidade de mesa/mão, hash canônico declarado, eventos, PTS e flags. Prioriza **conferência humana** por observações ausentes, baixa confiança não calibrada e alertas temporais; nunca interpreta pontos como probabilidade de erro ou EV. Gera JSON e HTML local sem JavaScript, com escaping e CSP. Rejeita caminhos fora da pasta, symlinks, chaves JSON duplicadas, NaN, relatórios incompatíveis, arquivos preexistentes e reivindicações indevidas de validação.
- `offline_ffmpeg_benchmark_matrix.py`: compara decodificação completa com FFprobe+seeks usando vídeos **sintéticos** MPEG-4 160×120, combinações limitadas de duração/GOP/quantidade de frames e 2–4 repetições. Relata mediana e fallback sem selecionar automaticamente a estratégia.
- Testes novos: `test_offline_hand_evidence_review_queue.py` e `test_offline_ffmpeg_benchmark_matrix.py`.

## Testes locais

- `python -m unittest discover -p 'test_*.py' -v` no diretório `video_analyzer` do pacote de regressão local do Ciclo 131, acrescido dos arquivos do Ciclo 132: **303 testes aprovados** em 18,431 segundos. Não equivale à suíte completa do GitHub.
- Benchmark 6 e 12 s, GOP 10/60, 1/5 frames, 2 repetições: **8 configurações e 16 execuções sintéticas**, todos os PNGs e PTS comparados exatamente pelo módulo subjacente. Neste ambiente, a decodificação completa apresentou mediana menor nas oito configurações. Tempos em `benchmark_matrix.json`.
- Demonstração de 4 mesas sintéticas: fila ordenada por pontos de conferência (mesas 4, 2, 3, 1), **zero autorização** de equity/EV ou seleção automática. O vídeo original não existe nesta demonstração; hashes de origem são valores sintéticos declarados.

## Não verificado

- OCR, reconstrução de mãos, calibração das confianças, precisão de equity/EV em vídeos reais, exportação de clipes em sessões reais e performance em 40–60 minutos.
- Relatórios consumidos podem ter sido alterados antes de entrar na fila; o gerador revalida sua consistência estrutural, mas não reprocessa vídeo, crops ou MP4. SHA de origem é uma declaração.
- Resultados do benchmark não justificam escolha automática de estratégia em produção.

## Próximo

1. Integrar a fila à interface de revisão e à reconstrução de mãos com evidência de origem validada.
2. Coletar vídeo autorizado de 3–5 min com anotação humana para medir OCR, segmentação e precisão.
3. Benchmark com codec/resolução representativos e tempos de sessão maiores, mantendo limites de recursos.
