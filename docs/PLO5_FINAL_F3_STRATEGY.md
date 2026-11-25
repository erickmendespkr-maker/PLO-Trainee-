# Finalização F3 — integração opcional do solver PLO5 (25/11/2026)

## Entregas
- plo5_river_accelerated.py: converte políticas da variante CFR+ em relatório compatível com o solver restrito anterior; recalcula EVs, marginais e gap com a matriz de pares preparada pelo modelo existente. Mantém todas as flags de não certificação e o hash do jogo original.
- plo5_river_cache_open.py: abre SQLite separado e rejeita bancos com objetos/colunas incompatíveis, links simbólicos e caminhos protegidos.
- plo5_strategy_integration.py: opção --river-engine cfr-plus, --river-cache CAMINHO opcional. Mantém vanilla por padrão e as checagens anteriores de contexto, evidência, sizing, rake e identidade. O cache só é aberto para extensão river. Nenhum backend de produção alterado por padrão.

    python video_analyzer/plo5_strategy_integration.py JOBS_DB JOB_ID DRAFTS REVIEW EQUITY_DB STRATEGY_DB EXTENSION OUTPUT --river-engine cfr-plus --river-cache solver_cache.sqlite

O cache armazena políticas para matrizes matemáticas idênticas e não resultados GTO reais. As escalas em BB e hashes de cenário são reconstruídos a cada chamada. Sem inferência de ranges ou autorização estratégica real.

## Validação
- Linux Python 3.13.5: 22 testes aprovados (12 regressões + 6 do adaptador com matriz preparada simulada + 4 de abertura do cache), 0,025 s.
- 5 testes adicionais em 0,029 s com os quatro arquivos do motor matemático copiados do GitHub e hashes Git conferidos: offline_omaha_showdown, plo5_rank_cache, plo5_evaluator e plo5_river_solver. Apenas imports de CLI sem uso e o guard genérico need foram simulados para esse ensaio isolado. Testes de ranges, blockers, PLO5, identidade do jogo, EV e compatibilidade de campos. Total 27 testes distintos, 15 novos. Não é teste de evidência ponta a ponta.
- 101 repetições do cenário polar de matriz preparada simulada: mediana 0,781746 ms sem cache, 0,064299 ms com SQLite em memória, 12,16x; resultados iguais excluindo a flag cache_hit. 300 iterações e gap 0,0097264072 do pote. Não inclui preparação de cartas, I/O de disco, OCR, ingestão ou relatório de sessão completa.
- Arquivo de roteamento modificado compilado no Linux, hash igual ao blob publicado; execução integral desse roteamento ainda não realizada.

## Pendências
F3 parcial. Pré-flop, stackoff, multiway, implied odds, draws, blockers e demais modelos existentes não foram alterados neste ciclo; faltam validação completa e cobertura de decisões reais. Database original de equity ausente, bibliotecas externas ainda não instaladas, fontes GTO autorizadas não importadas, vídeos reais não recuperados e clone integral bloqueado por DNS. Nenhum erro estratégico real certificado. Preservar F1/F2 e pendências originais. F4 é o próximo disparo planejado. Nenhuma mudança em main, deploy ou automação.
