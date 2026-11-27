# Bloco 12 — equity exata no turn

Motor offline exclusivo PLO5, contra um adversário uniforme entre as mãos legais. Reutiliza o ranking das duplas de cartas privadas com as quatro cartas comunitárias iniciais. Para cada river possível, completa os rankings com as seis novas trincas do board; conta mãos adversárias de cinco cartas por cliques em dois grafos de compatibilidade (todas as duplas inferiores ao Hero; todas inferiores ou iguais). A diferença conta empates, e o complemento conta derrotas. Sem Monte Carlo, sem API externa. Não considera ranges condicionados, múltiplos adversários, ações, rake ou GTO.

Teste Linux com Ks Js 8s 6c 5c / 7d Ac 3d 6d (cartas visuais de mão anteriormente foldada, cenário hipotético HU uniforme, não resultado real): 43 rivers, 36.578.724 resultados conjuntos river/mão adversária, 9.225.429 vitórias, 665.524 empates, 26.687.771 derrotas, equity 26,130465895967286%. Todos os 43 resultados por river coincidiram com o motor exato anterior. Tempo em uma execução com cache de rankings inicialmente vazio: 0,8433 s otimizado vs 8,3643 s usando 43 chamadas do motor anterior (9,92x). Não benchmark de sessão completa.

18 testes selecionados aprovados em 4,711 s: 6 novos e 12 regressões de river/auditoria de ranking. Inclui comparação com oráculo independente em 12 cenários reduzidos, contagem de cliques contra enumeração e validação de cartas. Blobs locais/remotos idênticos: 13802c4f262add90005e2e109b2e31bafac78f11 e 1f0dd4a1fbb625306a2347d62fd1d6fecbad9456. Main preservada.

Uso: python video_analyzer/plo5_exact_turn_equity.py --hero Ks Js 8s 6c 5c --board 7d Ac 3d 6d

Pendências: recuperar snapshot CSV original da base SolvePoker e auditar SQLite; integração PokerKit/PokerInfra ainda não validada; validação de mão Suprema, OCR, históricos e regressão integral permanecem abertas. Próximo: cálculo pré-flop/flop contra ranges explicitamente definidos com orçamento de amostragem e incerteza, base estratégica bloco 13. Não apresentar equity uniforme como recomendação de ação.
