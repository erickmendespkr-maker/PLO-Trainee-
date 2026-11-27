# PLO5 — Plano de macroblocos intensivos
Data: 27/11/2026. Base: 791501367854f4dd6e988ed68d0606380ce3e599.
Complementa o dossiê integral; não elimina pendências anteriores. Exclusivamente PLO5 offline pós-sessão. Não alterar main, não usar RTA, Gemini ou bases proprietárias sem autorização.

## Fila de execução
As capacidades abaixo são estimativas de tarefas possíveis, não quotas obrigatórias nem contagem de trabalho concluído. Não fragmentar artificialmente tarefas para atingir números. Cada grupo deve ser decomposto em implementações e verificações concretas conforme o estado atual do código.

| Macrobloco | Capacidade indicativa | Entregas e gates |
|---|---:|---|
| 01 — POST-GTO 05B | 50 | Recuperar fontes exatas; compilar CLI/kernel C++; adaptar terminais river; testar protocolo e inputs inválidos; comparar frequências, EV, BR e gaps Python/C++; ampliar oracles, blockers, tamanhos e stacks; registrar RSS/tempo e regressões. Gate: paridade medida, escopo e limitações explícitos. |
| 02 — 05C | 55 | Rake e sua base/cap; utilidades separadas quando soma variável; BR por jogador; ranges Bayes encadeáveis; provenance; manifesto de árvore, histórico, ações, reach; persistência/cache e integração com review. Gate: settlement e lookup reproduzíveis. |
| 03 — 06 | 60 | Chance river condicionada aos holdings; infosets sem vazamento; árvore turn; alcance e blockers; terminais all-in; CFR conjunto e comparação oracle; cache, orçamento e testes. Gate: fixture integrada com chance exata e BR validada. |
| 04 — 07 | 60 | Turn e river ordenados; chance sampling; abstração controlada; cálculo de nuts/draws; transições, ranges, cobertura; benchmark e validação holdout. Gate: consistência cross-street e erros quantificados. |
| 05 — 08 | 60 | 2–6 seats; pot layers, retorno, rake, all-in, folded blockers, ranges conjuntos; ganhos unilaterais/NashConv; regressões e performance. Gate: ledger conservativo e oracle reduzido; não afirmar convergência geral multiplayer. |
| 06 — 09 | 60 | Continuação pré-flop/pós-flop; teste PRE-GTO 42 e multiway V4; contexto e posições; RFI, call, 3/4-bet, stack-off; ranges por histórico; paridade e validação em jogos pequenos. Gate: integração demonstrada sem extrapolação HU para 6-max. |
| 07 — 10/11 | 60 | Censo/índice canônico e bijeção; shards/lookup/mmap; equity e ranks; store policies e migração; provenance/licenças/import CSV; fila, cache e geração sob demanda. Gate: recuperação exata, cobertura e orçamento de RAM/disco. Não materializar trilhões de estados. |
| 08 — Vídeo visual | 60 | Inventariar módulos; códigos/assinaturas visuais e perfis; cache exato e invalidação; layout dinâmico, PPPoker/Suprema, ROIs, cartas/naipe/nick/dealer/assentos; destaque/showdown; OCR fallback; Parte 01 dev e Parte 06 holdout; mensurar precisão e cobertura. Gate: dados incertos ficam desconhecidos. |
| 09 — Vídeo histórico | 60 | PTS, fronteiras, agrupamento; ordem das ações, blinds, stacks variáveis, bet sizing, folds, all-in; payouts, rebuy, retorno, side pots, ledger; trilha de evidência; reconstrução e testes em gravações. Gate: reconciliação financeira e histórico validado. |
| 10 — Review integrado | 60 | Contrato mão/decisão; match exato ao modelo; solver/lookup sob demanda; EV loss comparável, incerteza, UNSOLVED; prints, HTML PT-BR, leaks e clipes opcionais; regressões end-to-end. Gate: nenhuma inferência sem evidência e relatório reproduzível. |
| 11 — Performance | 55 | Perfil ponta a ponta; CPU/RAM/IO; kernels, subprocess persistente, cache, decodificação por lote, paralelismo limitado, fila retomável e regressão de qualidade; Windows 10/6 GB/SSD. Gate: medição real da meta 5–10 min/h, não inferência de microbenchmark. |
| 12 — Entrega | 60 | Baseline/holdout, sessão longa 3–4 mesas, acurácia por campo, fronteiras, cobertura, financeiro, regressão; interface, scripts CMD, instalador limpo, logs, manual e release. Gate: critérios de aceitação satisfeitos e limitações documentadas. |

Capacidade indicativa total: 700 tarefas. Não representa percentual ou promessa de conclusão em 12 turnos.

## Protocolo P/p/Prossiga
1. Conferir HEAD e pendências, selecionar macrobloco aberto; priorizar 01 (C++ river) e testes pré-flop/multiway independentes quando úteis.
2. Fazer o máximo de trabalho concreto que couber no ciclo: recuperar código, implementar, executar testes, corrigir, integrar, medir e publicar. Agrupar operações independentes; não reduzir qualidade para atingir contagem.
3. Se bloqueado, registrar erro real e passar para outra frente independente (inclusive vídeo, PRE-GTO e Windows). Não fingir execução nem reescrever fontes como se fossem checkout exato.
4. Verificar commits e preservar main. Registrar comandos, saídas, SHA, versões, escopo, limitações e próximo passo.
5. Se um macrobloco atingir todos os gates, iniciar o próximo no mesmo ciclo quando houver recursos. Se não, retomar suas tarefas abertas no próximo P; não declarar conclusão prematura.
6. Relatar apenas ações realmente realizadas, testes efetivamente executados e impedimentos. Não exigir confirmação para continuar trabalho autorizado. Sem promessas de execução futura fora de automação real.
