# Bloco 21 — Equity PLO5 (25/11/2026)

## Entrega

video_analyzer/plo5_equity.py utiliza evaluate do bloco 20 e _cards do núcleo de showdown. Hashes das dependências locais conferidos com os blobs publicados bcb148829e86214bd84ade8c24106661938a2ad7 e c1ebc5025bf9305d451576721d2721bfae4e6dfa. Nenhuma alteração nos avaliadores legados.

API Python: equity(hero, board, entries, method='auto', trials=2000, seed=0, max_exact=5000). Exatamente cinco privadas, board de 0/3/4/5 cartas, 1–10000 combinações explícitas de cinco cartas adversárias com pesos inteiros positivos de até 10^9 (massas relativas, não frequências GTO). Combinações duplicadas mesmo em ordem diferente, cartas inválidas ou range totalmente bloqueado são rejeitados. Remove combinações contendo cartas conhecidas e renormaliza; reporta quantidade e massa excluída. known_equity(hero, board, opponent, **options) usa uma holding fixa declarada. sensitivity(hero, board, scenarios, **options) compara 2–5 ranges nomeados e retorna amplitude de estimativas, não intervalo de confiança.

Cada holding legal tem C(42 - len(board), 5 - len(board)) runouts não ordenados; enumeração exata usa pesos inteiros e Fraction, equity = P(win)+P(tie)/2. Auto escolhe enumeração exata se estados <= orçamento (padrão 5000, máximo configurável 20000); caso contrário usa Monte Carlo. Método exact acima do teto é rejeitado. Monte Carlo usa sorteio IID de holding por massa inteira acumulada e amostra uniforme de runout sem reposição dentro de cada trial; seed reprodutível (0..2^32-1), 1–100000 trials. Ordem das holdings canonicalizada. Cache limitado de 2048 ranks do Hero por board. Relatório distingue massa inteira ponderada de contagem de simulações, probabilidades de vitória/empate/derrota, número de estados possíveis/avaliados e intervalo amostral conservador Hoeffding 95% (raio sqrt(log(40)/(2*trials)), truncado a [0,1]). Enumeração exata não tem erro amostral sob hipóteses declaradas. O intervalo não inclui incerteza do range, OCR ou seleção de modelo. A amplitude entre cenários não é garantia estatística.

Escopo: showdown heads-up condicionado a cartas/ranges explícitos e um pote comum, sem apostas futuras, multiway, rake, side pots, cartas mortas extras, ponderação estratégica ou inferência de adversário real. Não é GTO, EV, análise de sessão real nem importação de estratégia. O CSV SolvePoker permanece separado. Integração do pipeline estratégico em blocos 22–24.

## Verificações

8 novos testes aprovados (3,034 s); oráculo independente do bloco 20 verifica contagens de 38 runouts de turn e 1482 estados ponderados de flop. River ponderado: 60% da massa bloqueada, massa legal 4, win=1, tie=3, loss=0, equity 5/8 = 62,5%. Turn 9 wins, 3 ties, 26 losses, 21/76 = 27,6315789%. Flop massa 521 wins, 2042 ties, 401 losses, equity 257/494 = 52,0242915%. Pré-flop holding fixa: 2000 trials seed 42, 647 wins, 65 ties, 1288 losses, equity 33,975%, IC amostral [30,9382%,37,0118%], 2,2822 s na medição local única. Exato flop 1,3132 s; turn 0,0421 s; river 0,0021 s. Cenários distintos sintéticos, não uma mesma mão ou resultado de sessão. Testes adicionais: empate, royal, seed/invariância à ordem de range, orçamento e seleção automática, sensibilidade, entradas inválidas.

190 testes distintos selecionados aprovados em cinco execuções: 8 novos, 78 regressões estratégicas (0,563 s), 15 avaliador/financeiro (2,272 s), 47 ingestão/equity (17,680 s), 42 reconhecedores (16,208 s). Sem falhas ou skips nessas execuções. Ambiente de regressão anterior conserva os dois classificadores reproduzidos no bloco 13; não é a suíte integral do GitHub. Sem vídeo real ou benchmark Windows neste bloco.

## Estado

Bloco 21 concluído no escopo matemático heads-up descrito. Ponderação multiway e validação de hipóteses de range real continuam abertas; não extrapolar resultados HU a multiway. Preservar pendências 11B e 13–19. Próximo bloco 22: EV incremental de fold/call/bet/raise sob hipóteses explícitas, sizing, rake, baseline e incerteza. Sem mudanças em main, deploy, automação ou dados privados.
