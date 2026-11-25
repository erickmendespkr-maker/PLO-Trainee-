# Bloco 23 — comparação de EV e perda condicional PLO5 (25/11/2026)

## Implementação

video_analyzer/plo5_ev_comparison.py reutiliza analyze do bloco 22 (blob 58aad47e90dc3adad216d2d04330ec2a4dfa16fd). API compare(scenarios, chosen_action, **options): 1–5 hipóteses nomeadas com o esquema do bloco 22; chosen_action contém action e extra_chips, com extra positivo apenas para bet/raise e zero para fold/check/call. Recalcula EV com o motor existente, não aceita tabelas externas de EV como referência. Exige mesmas cartas privadas (ordem irrelevante), board na mesma ordem, pote, contribuições, stacks, BB, mínimo de raise, rake e conjunto de sizings; somente range e respostas por combinação podem variar entre hipóteses. Não substitui sizing ausente pelo mais próximo.

Calcula max(EV das alternativas modeladas)-EV da ação declarada, usando Fraction para ponto e empates exatos. Mantém todas as melhores ações empatadas e as possivelmente melhores dentro dos limites. Para a ação escolhida com intervalo [L_a,U_a] e rivais j, perda mínima=max(0,max_j(L_j-U_a)); máxima=max(0,max_j(U_j-L_a)). Exclui a própria ação dos rivais. Limites exatos usam as frações; intervalos Monte Carlo usam os limites marginais do bloco 22 com ajuste de arredondamento para fora. Classificação condicional: INFERIOR_UNDER_BOUNDS se limite inferior positivo; BEST_OR_TIED_UNDER_BOUNDS se limite superior zero; UNCERTAIN_UNDER_BOUNDS caso contrário; NO_MATCH para ação/sizing ausente; INSUFFICIENT_DATA quando não existem rivais. Não inventa perda zero para dados insuficientes.

Reporta alternativas modeladas, cobertura das hipóteses e ausência de cobertura integral do espaço de ações. A amplitude dos modelos não é IC estatístico; para n intervalos amostrais marginais de 95%, limite inferior de cobertura simultânea por união max(0,1-0.05*n), condicionado aos modelos declarados (sem pressupor independência). Não incorpora incerteza de escolha do range/resposta, nem prova uma estratégia de equilíbrio. Resultado financeiro, atribuição à variância e EV loss real permanecem null; nenhuma ação observada, erro estratégico, GTO ou corte automático é verificado/autorizado.

## Testes

207 testes distintos selecionados aprovados em cinco execuções: 9 novos (0,080 s), 78 estratégicos (0,381 s), 31 matemáticos/financeiros (5,567 s), 47 ingestão/equity (17,707 s), 42 reconhecedores (16,394 s). Sem falhas ou skips nesses grupos. Núcleos dos blocos 20–22 conferidos contra hashes remotos. Regressões de vídeo preservam os classificadores parcialmente reproduzidos no bloco 13; não é a suíte integral do repositório.

Fixture exato do bloco 22: fold EV 0 BB, call e raise extra 40 fichas EV 5,125 BB; perda condicional do fold 41/8 BB, call/raise empatados. Com hipótese alternativa de fold adversário certo, perda condicional do call 4,875 BB, amplitude entre dois modelos [0,4,875]. Monte Carlo de 20 trials, dois intervalos marginais, cobertura conjunta inferior 90% sob hipóteses; decisão incerta. Testes de sizing exato ausente, múltiplos sizings, ausência de rival, incompatibilidade de contexto, tipos inválidos e separação de resultado financeiro/variância.

## Estado

Bloco 23 concluído no escopo de comparação matemática condicional heads-up. Sem avaliação de mão real, GTO, estratégia multiway, apostas futuras ou prova de cobertura completa. Preservar pendências 11B e 13–19 e extensão multiway. Próximo bloco 24: integração com a database, decisões reconstruídas e motor de cálculo, lookup estrito sem misturar contextos. Não converter equity de partida em frequência ou EV GTO. Sem alteração em main, deploy, automação ou dados privados.
