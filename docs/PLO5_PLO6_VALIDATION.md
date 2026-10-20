# PLO Trainee — plano de validação PLO5/PLO6

## Objetivo
Construir um treinador offline para Pot-Limit Omaha de 5 e 6 cartas, sem automação de mesas reais.

## Estado observado no fork (20/10/2026)
- Motor TypeScript Poker Kernel presente.
- Arquivos de regras, baralho, Pot-Limit, gerenciamento de potes e showdown presentes.
- Nenhum diretório de testes identificado na árvore da branch main.
- package.json define build via TypeScript, mas não define comando test.
- Build e execução dos testes ainda NÃO foram verificados.

## Critérios de aceite para o primeiro MVP
1. Distribuir exatamente 5 cartas privadas em PLO5 e 6 em PLO6, sem cartas duplicadas.
2. Avaliar showdown usando **exatamente 2 cartas privadas e 3 comunitárias**.
3. Validar sequência preflop/flop/turn/river/showdown, inclusive folds e all-ins.
4. Respeitar limite de raise Pot-Limit, stacks e side pots.
5. Permitir simulações reproduzíveis com semente e registrar resultados.
6. Calcular equity com intervalos de confiança e tratamento explícito de empates.
7. Testar cenários com múltiplos adversários e resultados conhecidos por enumeração.
8. Apresentar recomendações como estimativas, nunca como garantias de lucro.

## Próximo ciclo técnico
- Inspecionar PokerVariantFactory, ShowdownHandler e PotLimitBetHandler.
- Adicionar testes determinísticos de regras para PLO5/PLO6.
- Implementar simulador Monte Carlo sem interface e validar contra casos conhecidos.
- Criar interface de treinamento após validação do motor.

## Segurança e governança
- Não integrar a sites de pôquer nem automatizar apostas reais.
- Manter mudanças nesta branch até revisão e testes.
- Respeitar licença AGPL-3.0 do código original.
