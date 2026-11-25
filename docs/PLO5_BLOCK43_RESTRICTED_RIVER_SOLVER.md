# Bloco 43 — fontes estratégicas e solver experimental PLO5 (25/11/2026)

## Fontes externas reavaliadas

- https://github.com/jejellyroll-fr/poker-eval : documentação declara árvores PLO5, CFR, exportação JSON/CSV e build CPU com BUILD_GPU=OFF; licença histórica GPLv3+ e termos de material posterior em LICENSE. Tentativa local de git ls-remote falhou por DNS de github.com. Não foi baixado, compilado, testado nem integrado. Revisão por componente e validação de convergência continuam pendentes.
- https://github.com/pokerinfra/poker-eval : avaliador/equity Rust/WASM com suporte declarado a Omaha5 e licença MIT, candidato a oráculo/otimização futura, não fonte de estratégia. Não compilado nem testado.
- https://github.com/nicoseijas/gto-research : pesquisa sobre CFR aplicado ao PLO5; os motores são declarados fechados. Referência metodológica apenas, sem código integrado.
- https://plospot.com/data-and-method.html : descreve exportações preflop de MonkerSolver, árvores e diferentes configurações. Não publica métrica de exploitability; não fornece solução postflop nessa base. Não foi encontrada autorização explícita de importação/redistribuição para nosso programa nesta revisão. Não houve raspagem, download de ranges, cópia de dados ou uso de credenciais. Manter fonte pendente. SolvePoker continua como snapshot de equity, não solução estratégica.

## Implementação própria

video_analyzer/plo5_river_solver.py resolve por regret matching tabular um jogo restrito HU river PLO5, com ranges explícitos de até 128 holdings por jogador, pares de cinco privadas disjuntos condicionados ao board e massa conjunta proporcional ao produto dos pesos inteiros. Exclui cartas bloqueadas pelo board e conflitos entre mãos; avalia regra exata 2+3 com núcleo existente. Não infere ranges a partir da gravação. Entrada exige variant=5, board de cinco cartas, pot_chips, bet_chips, hero_stack_chips, opponent_stack_chips, bb_chips, hero_range e opponent_range. Apenas check que encerra a ação em showdown, ou bet de tamanho único fixo <= pote e stacks; adversário após bet pode fold/call, sem raise. Sem rake, ação após check, multiway, streets anteriores, side pots ou árvore completa. Não é solução GTO geral, nem estratégia 6-max/preflop.

Payoffs do Hero a partir da decisão com pote inicial sunk: check qP, bet/fold P, bet/call q(P+2B)-B, q=1/0.5/0; payoff do adversário complementar no jogo de soma constante P. Normaliza por pote e calcula regrets contrafactuais com pesos conjuntos, estratégia média uniforme em iterações (uma decisão por jogador). Calcula melhores respostas globais contra as estratégias médias, limites inferior/superior e gap em BB e fração do pote, em ponto flutuante; não confundir gap com EV loss individual ou certificado rigoroso de precisão numérica. Indicador de gap <=1% do pote é critério de diagnóstico escolhido para esta árvore, não certificação GTO. Orçamento: 1–50000 iterações, <=4096 pares candidatos e <=4000000 produtos iteração x par legal. Produz JSON com contexto, hash da entrada, frequências condicionais e EVs por ação/holding, marginais, pesos e limites. CLI:

    python video_analyzer/plo5_river_solver.py game.json novo_resultado.json --iterations 20000

Não altera a database estratégica v4, não ativa importação real, não permite que frequências deste modelo sejam usadas como referência certificada. Mantém gto_solution=false, production_strategy_authorized=false, range_assumptions_verified=false, video_verified=false e strategic_error_established=false. Sem dependências novas.

## Teste analítico e regressões

Fixture sintético: pote 10 BB, bet 10 BB, board 2c 4d 7h 9s Jc; Hero possui uma holding AA (peso 1) e uma QQ (peso 2), adversário KK (peso 1), sem conflitos; AA ganha, QQ perde. No jogo restrito o equilíbrio tem bet AA 100%, bet QQ 25%, call KK 50%, valor Hero 5 BB. Com 20000 iterações: bet AA 99,9975%, bet QQ 24,6514%, call KK 50,2658%, valor 5,00008164 BB, limites 4,97675821–5,00885840 BB, gap 0,03210018 BB (0,32100184% do pote). Nenhuma alegação sobre ranges reais. Testes também verificam remoção conjunta de blockers com peso de entrada 12 e peso legal 9, vencedor único conhecido, entradas inválidas/orçamento, determinismo e limites de melhor resposta.

83 testes selecionados distintos passaram em 3,749 s: cinco novos do solver, mais 78 de evaluator, equity, EV, comparação, board, multiway, stackoff e preflop context. Sem falhas ou skips. Os cinco novos também passaram isoladamente em 0,047 s. Não foi repetida a suíte completa anterior. Blobs finais dos dois arquivos Python conferidos com locais testados.

## Estado

Bloco 43 parcial. Solver experimental restrito implementado e testado; fonte estratégica externa autorizada e árvore completa preflop/6-max continuam indisponíveis. Todas as 18 pendências originais e blocos 40–42 permanecem; bloco 43 também parcial. Próximo bloco 44: integração dos contextos e modelos matemáticos com evidência revisada, sem promover hipóteses a GTO. Nenhuma alteração em main, deploy, automação ou dados privados.
