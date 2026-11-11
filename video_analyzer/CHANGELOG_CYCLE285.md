# Ciclo 285 — 11/11/2026 — equity Omaha independente (cenário restrito)

## FEITO E TESTADO
- Consultados `docs/VIDEO_ANALYZER_SCOPE.md`, `docs/PLO_MASTERMIND_TECHNICAL_REFERENCE.md` e a branch `feature/plo5-plo6-training` (HEAD inicial `9c9ec9ddf044cf2421af049d722715a0847c4edd`).
- Implementado `offline_omaha_equity.py` com avaliador independente de mãos de cinco cartas, regra Omaha **exatamente duas privadas e três comunitárias**, suporte a PLO5/PLO6, validação de cartas duplicadas, enumeração exata de *runouts* com teto configurável e amostragem Monte Carlo reproduzível por semente.
- Modelo restrito a **heads-up com cartas do oponente explicitamente fornecidas**; somente as cartas futuras do board são amostradas. Não inferir ranges, cartas ocultas, rake, side pots, ações ou GTO.
- Equity considera vitória = 1, empate = 0,5 e derrota = 0. Intervalo de 95% pelo limite conservador de Hoeffding para resultados independentes em [0,1]. Não representa incerteza do range escolhido.
- **16/16 testes sintéticos locais aprovados** após corrigir um teste que esperava incorretamente que duas cartas privadas de paus não formassem straight flush com três comunitárias. Cobertura: wheel, royal, quadra, full house, restrição de duas cartas privadas, empate exato, semente, limites de confiança, cartas duplicadas, parâmetros inválidos e PLO6.
- Publicados módulo e testes na branch autorizada. Não foi alterada a main nem houve gastos.

## NÃO VERIFICADO
- Os testes locais foram executados em arquivos de trabalho antes da publicação; a versão remota exata ainda não foi reexecutada em checkout completo nem em CI.
- A gravação PLO5 real não foi processada neste ciclo; sem anotações humanas, não há reconstrução ou equity de mão real.
- O motor não suporta ainda ranges probabilísticos, múltiplos oponentes, side pots, fold equity ou EV de raise. Monte Carlo não é CFR/GTO.

## PENDÊNCIAS MINHAS
- Testar a árvore publicada integralmente e confrontar casos sintéticos de turn/river com enumeração exata e amostragem de maior N.
- Integrar holdings verificadas com os históricos e a auditoria de evidências sem promover hipóteses a fatos.
- Revisar duas a cinco mãos reais e medir precisão de OCR quando os quadros estiverem acessíveis.

## PRÓXIMO CICLO
1. Adicionar ranges explícitos com pesos e exclusão de blockers, sempre relatando hipóteses e massa rejeitada.
2. Criar benchmark Monte Carlo vs enumeração exata para board com quatro cartas e documentar tempo/erro.
3. Conectar a saída matemática a um relatório offline com SHA/seed/iterações e decisão de exportar cortes apenas após revisão.
