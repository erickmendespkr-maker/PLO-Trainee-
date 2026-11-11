# Ciclo 287 — 11/11/2026 — EV condicional integrado à equity ponderada

## FEITO E TESTADO
- Consultados `docs/VIDEO_ANALYZER_SCOPE.md`, `docs/PLO_MASTERMIND_TECHNICAL_REFERENCE.md`, `offline_weighted_ranges.py`, `offline_omaha_equity.py` e `offline_conditional_call_sensitivity.py` na branch autorizada.
- Criado `video_analyzer/offline_weighted_call_ev.py`: conecta os resultados de equity PLO5/PLO6 contra holdings ponderados ao cálculo `EV_call = q*(P+C)-C`, sob condições estritas de heads-up, showdown após call, sem rake, side pots nem apostas futuras.
- Para river, usa enumeração ponderada exata; nas demais streets, Monte Carlo do módulo existente, com seed, trials, intervalo Hoeffding e registro de blockers. Intervalos de EV são transformações dos intervalos de equity; não representam incerteza dos ranges assumidos.
- O resultado bloqueia alegações de verificação de mão real, erro estratégico, seleção automática e GTO. Ranges fornecidos manualmente são hipóteses, não OCR.
- Criado `video_analyzer/test_offline_weighted_call_ev.py` com 15 testes sintéticos propostos (identidade EV, river exato, reprodutibilidade, PLO6, blockers e rejeições).
- **Verificação realizada:** os dois arquivos foram criados via API GitHub exclusivamente na branch `feature/plo5-plo6-training`. **Os 15 testes ainda não foram executados**; não os contabilizar como aprovados.

## NÃO VERIFICADO
- Ambiente de execução local sem acesso DNS a github.com; não houve checkout exato, pytest/unittest local com os bytes publicados nem CI remoto.
- Não houve acesso à gravação PLO5 original nesta execução; sem novas mãos reconstruídas, acurácia OCR ou cortes MP4.
- Não foram testados adversários múltiplos, rake, side pots, raise EV ou ranges derivados de observações reais. Monte Carlo não é GTO.

## PENDÊNCIAS MINHAS
1. Executar `cd video_analyzer && python -m unittest -v test_offline_weighted_call_ev` na árvore exata da branch; corrigir quaisquer falhas.
2. Integrar a saída matemática ao gate de evidência da mão e ao compositor de clipes, sem atribuir ranges hipotéticos à jogada.
3. Revisar manualmente 2–5 mãos reais quando os quadros da gravação estiverem acessíveis.

## PRÓXIMO CICLO
- Validar e depurar a suíte no checkout real, ampliar benchmarks exatos de turn/river e construir relatório auditável de equity/EV por mão revisada.
- Continuar sem trainer jogável, assistência ao vivo, scraping PLO Mastermind, alteração de main ou custos.
