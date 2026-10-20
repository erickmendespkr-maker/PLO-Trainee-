# Auditoria inicial — 20/10/2026

## Confirmado por leitura do código
- `PokerKernel.getHoleCardCount` distribui 5 cartas para PLO5 e 6 para PLO6.
- `solveOmahaHand` enumera pares privados e trios comunitários, preservando a regra 2+3.
- `Deck` usa baralho de 52 cartas e embaralhamento Fisher–Yates com `crypto.randomInt`.
- `PotLimitBetHandler` contém fórmulas de limite de aposta e raise que requerem testes específicos.

## Defeito provável — prioridade alta
Em `PokerKernel.solveOmahaHand`, a escolha da melhor mão usa apenas `hand.rank > bestHand.rank`. No pokersolver, mãos da mesma categoria podem ter kickers diferentes; comparar só `rank` pode selecionar a combinação inferior. **Não corrigir sem teste de regressão**. Criar caso em que duas combinações formam um par, mas a segunda possui kickers superiores, e validar comparação por `Hand.winners([candidate, bestHand])` ou mecanismo equivalente da biblioteca.

## Outros riscos a validar
- Quando há menos de 3 cartas comunitárias, `solveOmahaHand` pode retornar null; verificar chamadas no pré-flop.
- `PotLimitBetHandler.getMaxBet` limita pelo stack de um adversário encontrado; verificar se é regra pretendida.
- `getMaxRaise` possui fórmulas diferentes para heads-up e multiway; confrontar com casos de pote e aposta, inclusive blinds, side pots e all-in.
- `RITShowdownHandler` requer teste com múltiplos side pots e duas boards.

## Critérios do próximo commit de código
1. Adicionar testes de regressão para comparação de mãos da mesma categoria.
2. Corrigir escolha da melhor combinação Omaha.
3. Testar cálculo de limite Pot-Limit com exemplos reproduzíveis.
4. Só declarar aprovação após executar os testes.
