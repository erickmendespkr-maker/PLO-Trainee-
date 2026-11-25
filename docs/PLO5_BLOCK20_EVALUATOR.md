# Bloco 20 — Avaliador matemático PLO5 (25/11/2026)

## Entrega

video_analyzer/plo5_evaluator.py reutiliza _cards e _five de offline_omaha_showdown.py (blob c1ebc5025bf9305d451576721d2721bfae4e6dfa), sem modificar os avaliadores legados. evaluate(hole, board) exige exatamente cinco cartas privadas e 3/4/5 cartas comunitárias, todas válidas e distintas. Calcula a melhor mão feita atual pela regra 2+3, enumerando 10/40/100 combinações legais no flop/turn/river. Retorna rank lexicográfico, categoria, duas privadas e três comunitárias utilizadas (testemunha determinística por ordenação dos cartões, não enumeração de todas as testemunhas empatadas). Pré-flop não é mão feita e é rejeitado nesta interface. showdown(hands, board) exige 2–6 mãos completas e cinco cartas comunitárias, sem sobreposição; retorna ranks, índices dos vencedores e frações exatas de um pote comum entre jogadores declarados elegíveis. Não modela potes laterais, rake ou arredondamento de fichas. Não identifica jogadores elegíveis automaticamente. Nenhum resultado de vídeo verificado, equity futura, EV ou GTO é declarado.

## Verificação independente

test_plo5_evaluator.py implementa oráculo próprio por padrão de multiplicidades, diferença entre ranks consecutivos e enumeração das combinações de cinco cartas da união privada/comunitária filtradas por proveniência. Não é biblioteca externa nem Poker-Eval. Verifica 7462 representantes de classes de ranks/flush, ponderados pelas atribuições possíveis de naipes; total 2598960 combinações físicas representadas (não enumeradas individualmente). Contagens de categoria da menor à maior: 1302540, 1098240, 123552, 54912, 10200, 5108, 3744, 624, 40. Todos os ranks e contagens coincidiram com o oráculo e distribuição esperada. 240 distribuições pseudoaleatórias reprodutíveis (seed 20261125, 2–6 jogadores, 960 mãos privadas) => 2880 comparações de rank flop/turn/river e 240 comparações de vencedores; frações somam exatamente 1. Inclui royal, wheel, kicker, empate triplo, proibição de board-only e flush com uma privada, invariância de ordem e rejeição de cartas inválidas.

Benchmark Python 3.13.5 x86_64, 1000 mãos no river com seed 42 e baralho completo: 100000 combinações legais avaliadas em 0,519441 s (1925,1 mãos/s); legado 0,516250 s, 1000/1000 ranks idênticos. Medição local única, não promessa de desempenho no notebook Windows nem de simulação de equity. A interface estrita agrega validação e testemunha, não aceleração do algoritmo.

## Testes locais

182 testes selecionados aprovados em quatro execuções: 7 novos (2,345 s), 78 estratégicos (0,353 s), 47 ingestão/equity (18,946 s), 50 reconhecedores e financeiro (15,859 s). Nenhuma falha ou skip nas quatro execuções; regressões preservam o ambiente dos blocos anteriores incluindo as reproduções parciais de classificadores do bloco 13. Não é a suíte integral do repositório. Núcleo de showdown recuperado integralmente pelo conector, hash local conferido. Os testes novos são matemáticos com dados sintéticos válidos, não reconhecimento de cartas de sessões reais.

## Estado

Bloco 20 concluído no escopo de avaliação matemática de mãos conhecidas PLO5. Próximo bloco 21: ranges ponderados, blockers, enumeração exata e Monte Carlo, incerteza amostral e sensibilidade a hipóteses. Preservar pendências do bloco 11B (GTO autorizado e compilação/execução Poker-Eval), 13–19 (calibração, reconstrução, pagamentos e reconciliação reais). Ainda não integra a nova interface aos cálculos de equity legados nem ao pipeline de revisão real; integração em blocos 21–24. Sem mudanças em main, deploy, automação ou dados privados.
