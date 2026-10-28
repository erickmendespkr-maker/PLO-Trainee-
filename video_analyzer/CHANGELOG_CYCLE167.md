# Ciclo 167 — relatório consolidado offline de sessão revisada

Escopo: `docs/VIDEO_ANALYZER_SCOPE.md`. O módulo `offline_session_consolidated_report.py` consome gravação, diretório de MP4, pacote de revisão, anotações manuais, revisão consolidada e relatório do bloqueio de EV. Produz **novos** JSON e HTML locais, somente leitura. Não seleciona cortes, não recalcula equity/EV e não recomenda jogadas.

## Garantias e limites

- Recalcula a interpretação do bloqueio usando `offline_review_ev_gate.validate` e exige igualdade JSON canônica (preservando tipos) com o gate fornecido. Rejeita gate obsoleto, adulteração de gravação, clipes e revisões, chaves duplicadas, links simbólicos e sobrescrita.
- Agrupa decisões pela identidade `(mesa, mão)`, sem duplicar clipes para múltiplas decisões da mesma mão. Mantém PLO5/PLO6, timestamps disponíveis, identificadores, hashes e hipóteses de ranges **não verificadas**.
- Mostra intervalo de EV **apenas** quando a revisão humana declara a observação confirmada; corrigidas, inconclusivas e pendentes têm EV suprimido. A confirmação não valida os ranges nem o EV.
- HTML local sem scripts/rede, com escape de campos não confiáveis e CSP. JSON e HTML são publicados como arquivos novos, sem editar os dados de entrada.
- O relatório não realiza OCR, segmentação, validação da ação legal, análise matemática independente, classificação de erro ou autenticação do revisor.

## Testes

- **33/33 testes locais aprovados**: 21 testes do novo módulo e 12 de regressão do gate, usando FFmpeg/FFprobe e quatro MP4 sintéticos. Incluem quatro mesas, dois tipos PLO, quatro estados de revisão, cinco decisões distribuídas por quatro mãos, adulteração, XSS, integridade, ausência de sobrescrita e repetibilidade.
- Demonstração com quatro clipes sintéticos e um relatório de quatro decisões: uma confirmada, uma corrigida, uma inconclusiva e uma pendente. Apenas a confirmada exibe EV hipotético.
- SHA Git dos arquivos Python publicados conferido com os arquivos testados. **Não** foi executada a suíte completa do repositório, nem os testes contra os bytes exatos da variante remota de `offline_human_observation_review.py`. GitHub Actions não utilizado.

## Exemplo

```bash
python video_analyzer/offline_session_consolidated_report.py \
  recording.mp4 exported_batch/ session_review.json manual_annotations.json \
  reviewed_observations.json ev_gate.json new_summary.json new_summary.html
```

## Bloqueios

Falta gravação real autorizada e anotada de 3–5 minutos para calibrar OCR e reconstrução; não há validação de sessões reais de 40–60 minutos ou de quatro mesas reais. Sem gastos, credenciais, produção, integração com pôquer real ou alterações em `main`.
