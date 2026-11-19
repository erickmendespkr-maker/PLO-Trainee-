# Ciclo: análise EV condicionada a ranges (18/11/2026)

Arquivos: `video_analyzer/offline_ev_scenarios.py`, `video_analyzer/test_offline_ev_scenarios.py`.

## Entrega
Calculadora incremental de call heads-up com pot odds, rake proporcional simplificado, e análise de sensibilidade para múltiplos cenários de equity fornecidos pelo analista. Cada cenário mantém seu rótulo e EV; o resultado informa se todos os cenários são positivos, negativos ou dependentes do range. **Não** calcula GTO nem deduz ranges de cartas ocultas.

## Validação e limites
Um protótipo local independente, de mesma matemática e cobertura de 10 casos sintéticos, passou 10/10 testes Python. O código publicado foi escrito em commits separados e não foi executado no ambiente do repositório nesta execução; testes de CI e comparação exata com PokerInfra continuam pendentes.

Nenhum MP4 de gravação real estava montado em `/mnt/data` nesta execução; o vídeo descrito no escopo não foi reprocessado. O processamento de OCR, cartas e ações não é validado por esta entrega.

## Convenções
`pot_before_call_bb` inclui a aposta adversária, mas exclui a call do herói; `call_cost_bb` é o custo adicional; `equity` é fração do pote final, não chance bruta de vitória. `call_ev = equity*(pot+call)*(1-rake)-call`. Assume heads-up, realização integral de equity, sem side pots ou apostas futuras. Rake é proporcional ao pote final e não possui cap. **Não usar para avaliar definitivamente uma decisão multiway ou com apostas futuras.**

## Próximo passo
Integrar ao relatório somente quando cartas, pote e custo da call forem revisados e ranges explícitos tiverem sido fornecidos. Adicionar testes integrados do pacote npm `pi-poker-eval`, seed reproduzível, intervalo de confiança e testes reais anotados.
