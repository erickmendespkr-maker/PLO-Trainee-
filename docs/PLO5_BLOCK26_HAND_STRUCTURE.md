# Bloco 26 — estrutura das mãos PLO5 (25/11/2026)

## Entrega

video_analyzer/plo5_hand_structure.py oferece describe(cards), exclusivamente cinco cartas distintas PLO5, reutilizando classify do bloco 25. Devolve identidade canônica, multiplicidades de ranks, quantidade de pares privados de mesmo rank, ranks distintos, Broadway, span e gaps em ordem de ás alto, dez pares privados possíveis e janelas de sequência incluindo wheel A2345. Cada janela informa os três ranks comunitários necessários. Distingue o número de pares capazes de sequência do número de triplas de ranks distintas; não confundir com flops físicos ou probabilidades. Compara a maior sequência do Hero em cada tripla com a maior sequência adversária possível sob remoção das cinco privadas do Hero; considera apenas sequências de ranks, não nuts absolutos (flush ou straight flush pode superar). Não considera ranges, cartas mortas adicionais ou probabilidades de ação. O ás baixo é tratado nas janelas de sequência, não nos gaps de ás alto.

Grupos de naipe com duas ou mais privadas: cartas, C(n,2) pares suited, disponibilidade de ás acompanhado, ranks superiores não vistos, 13-n cartas restantes e C(13-n,3) flops monotone daquele naipe, denominador C(47,3)=16215 sob conhecimento apenas das cinco privadas. Não converter em probabilidade de vencer. Blockers por rank: h cartas privadas, 4-h restantes, C(4-h,2) pares adversários de duas cartas restantes e 6-C(4-h,2) removidos; não representam mãos completas de cinco cartas. Mantém blockers físicos exatos. Explicações estruturais em português; equity, frequência e EV null, GTO/video_verified false. Sem pontuação de força arbitrária.

plo5_decision_analysis.py inclui hand_structure na referência pré-flop, reutilizando hand_class do mesmo cálculo e preservando o lookup agregado, exact_suit_match=False, frequência/EV null, controle de contexto e exclusão de estratégia sintética. Nenhum dado novo de solver ou alteração do SQLite.

## Testes

234 testes distintos selecionados aprovados em seis execuções locais: 8 novos (0,124 s), 19 integração/classes (3,245 s), 78 estratégicos (0,472 s), 40 matemáticos/financeiros (5,783 s), 47 ingestão/equity (18,142 s), 42 reconhecedores (16,263 s). Sem falhas ou skips nesses grupos. Não é a suíte integral do repositório; mantém os dois classificadores parciais do ambiente do bloco 13. Snapshot real de equity presente no teste de integração, SHA-256 conferido bddf887d08b9bfaeb55ab55e287b3398c31cf51620dde2ce9986baf7aeddaa9a. Dependências de classes, showdown e ponte de decisão conferidas por blob hash antes da alteração.

Testes novos: Broadway double-suited As Ks Qh Jh Tc com 10 pares capazes de sequência, 20 triplas de flop que completam sequência e 20 triplas de maior sequência possível; quadra privada de ases remove os seis pares AA físicos; wheel, gaps, self-blocking de 2–5 cartas suited, invariância de ordem e 24 permutações de naipes, comparação contra oráculo independente de ranks em 24 mãos seed 20261125 (até 286 triplas por mão), rejeição de entradas inválidas e integração sem misturar classe exata e equity agregada. Fixtures sintéticos matemáticos, não mãos reconhecidas de uma sessão real.

## Estado

Bloco 26 concluído no escopo descritivo pré-flop. Potencial de nuts absoluto por board, draws/redraws, ranges e avaliação estratégica por posição permanecem nos blocos seguintes; nenhuma frequência estratégica inferida. Preservar pendências 11B, 13–19 e 24, e ausência de mapeamento individual das linhas de equity do bloco 25. Próximo bloco 27: RFI, calls, defesa de blinds e 3-bet por posição e stack, somente dados e modelos sustentados. Sem mudanças em main, deploy, automação ou dados privados.
