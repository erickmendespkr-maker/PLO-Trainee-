# Ciclo 166 — bloqueio de EV após revisão humana

Escopo: `docs/VIDEO_ANALYZER_SCOPE.md`. Novo módulo `offline_review_ev_gate.py` associa o relatório de revisão, as anotações e o pacote de sessão aos hashes da gravação e dos MP4. Emite JSON/HTML offline e **não** recalcula equity/EV nem recomenda jogadas.

Estados por decisão:
- `conditional_model_only`: observação marcada como confirmada; EV original exibível **somente como hipótese**, com ranges não verificados.
- `blocked_stale_observation_requires_recalculation`: ação/timestamp corrigido; intervalo EV original omitido.
- `blocked_inconclusive_observation`: observação inconclusiva; intervalo EV omitido.
- `blocked_pending_review`: revisão pendente; intervalo EV omitido.

Valida integridade e vínculos dos relatórios, identidade e ordem das decisões, contagens, flags de não autenticação, hashes SHA-256 e clipes. Rejeita sobrescrita e symlinks de mídia. Não modifica originais. HTML usa escape e política CSP sem scripts/rede.

Testes: 12 testes portáteis novos com FFmpeg/FFprobe gerando quatro clipes sintéticos, mais 39 testes de regressão locais do módulo de revisão anterior: **51/51 aprovados** em Python 3.13. O teste de integração usa cópia local do módulo do Ciclo 164; a variante exata desse módulo atualmente publicada no GitHub não foi executada em conjunto. Há também 24 testes adicionais aprovados com os arquivos de demonstração locais, mas eles dependem de fixtures não incluídas no repositório e não compõem a suíte portátil publicada. Sem GitHub Actions.

Exemplo de execução (arquivos existentes, saídas novas):

```bash
python video_analyzer/offline_review_ev_gate.py \
  recording.mp4 exported_batch/ session_review.json manual_annotations.json \
  reviewed_observations.json ev_gate.json ev_gate.html
```

Bloqueios: falta vídeo real autorizado e anotado de 3–5 minutos para calibrar OCR; sessões reais de 40–60 minutos não validadas; ranges adversários e decisões não verificados; não há recálculo de EV após correção. A suíte completa do repositório não foi executada. Nenhum gasto, produção, credencial, `main` ou GitHub Actions alterado.
