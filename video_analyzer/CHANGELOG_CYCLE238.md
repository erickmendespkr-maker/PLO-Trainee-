# Ciclo 238 — índice offline da sessão

## Escopo e entrega

Novo módulo `video_analyzer/offline_ev_session_overview.py` que transforma o `batch_report.json` produzido por `offline_ev_batch_clips.py` em um índice HTML estático com links relativos para os MP4 e seus relatórios JSON.

Uso, depois da exportação em lote:

```bash
python video_analyzer/offline_ev_session_overview.py /caminho/para/diretorio_de_clipes
```

Saída: `session_overview.html` no diretório informado, sem sobrescrever arquivo existente. Não há dependências web, JavaScript, captura ao vivo ou acesso a contas de poker.

O índice mostra mesas, mãos, ações declaradas, diferenças condicionais de EV, clipes e decisões ignoradas. **Não** transforma OCR ou confirmação humana em evidência matemática autenticada. Ranges, seed, número de simulações e intervalos de confiança permanecem nos relatórios JSON de cada clipe.

## Integridade e limites

Antes de publicar o HTML, o módulo confere os hashes SHA-256 dos MP4, vínculos com vídeo e resumo originais, IDs e nomes seguros, proibição de symlinks para os clipes, limites de quantidade e existência de manifesto de exportação. Reconfere hashes antes da publicação atômica por hard link.

## Testes locais reproduzidos

- `python -m unittest -q test_offline_ev_session_overview`: 28 testes selecionados aprovados, incluindo 8 métodos novos e testes descobertos por importação.
- `python -m unittest -q test_offline_mc_input_contract test_offline_mc_equity test_offline_mc_action_ev test_offline_ev_decision_clip test_offline_ev_batch_clips test_offline_ev_session_overview`: 237 testes selecionados aprovados em ambiente Linux com FFmpeg.
- Geração de `session_overview.html` sobre quatro MP4 sintéticos do Ciclo 237.

A seleção do unittest inclui testes importados por outros módulos e não representa a suíte integral do repositório. Sem GitHub Actions.

## Não verificado

Não houve validação em gravações reais, sessões de 40–60 minutos, OCR de cartas reais, Windows ou navegador em modo `file://`. O índice HTML é apenas uma navegação local de artefatos já exportados. A análise de EV permanece condicional às hipóteses manuais e não é um veredito estratégico.

## Próximo ciclo

Vincular os clipes às regiões de cada mesa e oferecer um relatório mais detalhado por street e evidência visual, preservando rastreabilidade e incerteza. Continua faltando um vídeo autorizado e anotado de 3–5 minutos para medir reconhecimento visual.
