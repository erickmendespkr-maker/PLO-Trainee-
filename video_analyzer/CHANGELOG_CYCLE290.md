# Ciclo 290 — 11/11/2026 — limites de EV sob ranges hipotéticos

## FEITO E TESTADO
- Inspecionado o HEAD inicial `4f4cac84d8354d309178fca210821a0f384970d7`, além de `docs/VIDEO_ANALYZER_SCOPE.md`, `docs/PLO_MASTERMIND_TECHNICAL_REFERENCE.md`, motor de equity ponderada, ponte de EV e auditor.
- Criado `offline_ev_model_bounds.py`: transforma **intervalos condicionais de equity informados externamente** em intervalos de EV de call para cenários heads-up simplificados, com fold = 0 BB, sem rake, side pots ou apostas futuras. Usa `EV = q(P+C)-C`, `q_min=C/(P+C)`. Produz envelope dos cenários e classifica somente a comparação **dentro das hipóteses**: call em todos, fold em todos ou sensível/incerto.
- Implementadas validações de intervalos, valores finitos, IDs distintos, ausência de chaves extras e limites numéricos; não aceita dados de vídeo nem gera afirmação GTO.
- **16/16 testes locais aprovados**, executados em Python 3.13.5 com `python -m unittest -v test_offline_ev_model_bounds`. Foram exercitados limites, casos positivos/negativos, pot odds, cenários divergentes, valores NaN/infinito, booleanos, injeção de texto e schema inválido.
- Os dois arquivos publicados foram comparados por Git blob SHA com os arquivos testados localmente: `ec80903bded646dd1d96536e1da2fc6eb9036c5c` e `053f10804309fc3936bcdc6e4a900fad322fb2fc`, **correspondência exata**.
- Os commits desta execução foram feitos somente na branch `feature/plo5-plo6-training`. Nenhuma alteração em main, produção, credenciais ou gastos.

## NÃO VERIFICADO
- A suíte antiga de 15 testes de `offline_weighted_call_ev.py` e a integração de 10 testes do ciclo 289 continuam sem execução neste ambiente: `git ls-remote` falhou com `Could not resolve host: github.com`. A leitura/escrita por conector GitHub funcionou, mas não substitui checkout completo nem CI.
- Nenhum RAR ou MP4 de sessão real estava disponível em `/mnt/data` nesta execução; apenas o MP4 sintético de 7 segundos do ciclo 281. Não foi feita nova reconstrução de mãos, validação de OCR nem corte MP4 real.
- O novo módulo não recebe automaticamente o relatório do motor Monte Carlo. A integração de schemas ainda é pendência. Os intervalos de equity fornecidos não capturam a incerteza sobre a escolha dos ranges, e o envelope **não** é um intervalo de confiança estatístico.
- Nenhum resultado aqui constitui recomendação para jogo ao vivo ou solução GTO.

## PENDÊNCIAS MINHAS
1. Executar as suítes antigas no checkout da branch e corrigir falhas identificadas.
2. Criar adaptador validado entre `offline_weighted_call_ev.analyze`, `offline_ev_scenario_audit.audit` e `offline_ev_model_bounds.evaluate` sem perder proveniência e sem converter hipóteses em fatos.
3. Validar pelo menos 2–5 mãos anotadas da gravação autorizada quando estiver acessível, com timestamps e confiança por campo.
4. Ligar uma mão revisada ao exportador MP4 e manter `INSUFFICIENT_DATA` onde faltarem cartas, ações ou ranges.

## PRÓXIMO CICLO
- Priorizar integração de schema e testes cruzados entre equity/EV/auditoria/limites, seguidos de validação em checkout completo; não criar trainer jogável ou integração com poker real.
- Avançar no fluxo offline FFmpeg → revisão humana → histórico → matemática condicional → corte auditável.

Referência PLO Mastermind: somente conceitual pública; sem API presumida, scraping, dependências proprietárias ou GTO alegado.
