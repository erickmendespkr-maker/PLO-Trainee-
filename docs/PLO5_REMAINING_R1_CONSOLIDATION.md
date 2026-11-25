# R1 — Recuperação e consolidação PLO5 (25/11/2026)

## Entregas
- Auditoria independente de ranking em plo5_rank_audit.py, com testes. Enumera os 7.462 estados distintos de ranking de mãos de cinco cartas, ponderados pelas 2.598.960 combinações físicas; compara com o avaliador rápido. Testa PLO5 com exatamente duas cartas privadas e três comunitárias, flop/turn/river e empates.
- plo5_reference_audit.py: recuperação agora cria snapshot em diretório temporário, audita e só então publica por link sem sobrescrever. CSV original ainda obrigatório; não muda o gate de SHA do SQLite. Cinco testes novos, um com importador real rejeitando CSV não revisado, demais verificando atomicidade com fixtures.
- plo5_river_solver.py: importações de CLI movidas para main, guard local equivalente ao anterior. Núcleo matemático isolado da ingestão de vídeo, sem alterar o algoritmo.
- Seis módulos originais recuperados e conferidos com hashes de blobs: offline_omaha_showdown, plo5_evaluator, plo5_rank_cache, plo5_river_solver (antes do ajuste), plo5_hand_classes, plo5_equity_store; também teste original test_plo5_river_solver.

## Validação local
97 testes selecionados aprovados, 0 falhas, 0 erros, 0 skips, em 0,861 s. Inclui 11 novos testes, regressões dos incrementos, cinco testes originais do river e cinco comparações do acelerado usando o motor real sem mocks de imports. Alguns testes de interface e fluxo visual continuam com fixtures/mocks. Não é suíte integral.
Auditoria exaustiva de assinaturas: 7.462/7.462, zero divergências, 0,169 s. Auditoria determinística PLO5 (seed 20261125): 4.096 showdowns de 2–6 jogadores, 16.382 holdings, 49.146 verificações de street, 215 empates, zero divergências, 11,115 s. Não é benchmark de sessão, equity ou GTO.
Enumeração de órbitas pré-flop: 134.459 classes únicas, 2.598.960 combinações, 28.496 descritores, 20.449 descritores ambíguos. Nenhuma linha real de equity recuperada ou verificada.

## Bloqueios
Clone integral GitHub e download SolvePoker falharam por DNS. PokerKit ausente do cache local pip; pi-poker-eval ausente do Node. Sem instalação ou compilação externa. Nenhuma nova base estratégica autorizada disponível neste ciclo. Não houve compra, mudança em main, deploy ou automação. R1 parcial: preservar R1/F1–F5 e todas as pendências históricas. Próximo disparo R2 (reconhecimento real).
