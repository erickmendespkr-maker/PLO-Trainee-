# Finalização F1 — consolidação de referências PLO5 (25/11/2026)

Base consultada: cb7b515369b41f521726ad8c4e852ba972537135. Escopo offline, apenas PLO5, sem alteração do motor de produção.

## Entregas
- plo5_reference_audit.py: valida SHA-256 binário ou comparação exata linha a linha com o CSV revisado; verifica esquema, metadados, integridade, classes, massa física e índice de busca. A recuperação usa o importador existente. Se a versão SQLite gerar bytes diferentes, a auditoria lógica não altera o gate binário original do runner.
- plo5_external_check.py: comparação diferencial de vencedores de showdowns conhecidos (2–6 jogadores, cinco cartas privadas) com PokerKit e PokerInfra/pi-poker-eval. Adaptadores opcionais, sem ativação automática em produção. Não é solver.
- 11 testes novos aprovados no Linux (0,324 s); regressões locais anteriores: 6 do relatório visual e 6 do SingleFlight aprovados. Os testes de comparação usam backends simulados, não bibliotecas externas. Contagem independente por Burnside: 134459 órbitas e 2598960 combinações físicas; não constitui auditoria das linhas da fonte.

## Recuperação da referência
Fonte: https://solvepoker.app/plo5-starting-hand-rankings
CSV: https://solvepoker.app/data/plo5-hand-rankings.csv
Licença CC BY 4.0, atribuição SolvePoker (solvepoker.app). Equity vs adversário aleatório, sem mapeamento exato de naipes por linha ou frequências GTO.

    python video_analyzer/plo5_reference_audit.py data/plo5_equity.sqlite
    python video_analyzer/plo5_reference_audit.py data/plo5_equity.sqlite --csv plo5-hand-rankings.csv --recover

O segundo comando requer destino inexistente e CSV com SHA revisado. Snapshot anterior não localizado no ambiente local ou nas buscas do Drive. Download direto falhou (DNS; ferramenta web não aceita CSV). Nenhuma linha da base real auditada neste ciclo.

## Dependências externas
PokerKit (MIT): https://github.com/uoftcprg/pokerkit
PokerInfra (MIT): https://github.com/pokerinfra/poker-eval (Rust e WASM/JS; é o mesmo projeto pi-poker-eval).
Instalação externa e validação com pacotes reais pendentes; Linux não resolve DNS. Quando disponíveis:
    python video_analyzer/plo5_external_check.py pokerkit --cases 1024
    python video_analyzer/plo5_external_check.py pokerinfra --cases 1024
O segundo comando exige Node e pacote pi-poker-eval instalado localmente. Sem instalação automática, sem rede durante comparação.
A biblioteca histórica poker-eval distinta requer auditoria de compatibilidade PLO5 e licença. Não foi integrada. Nenhuma autorização de importação de ranges do PLOSpot ou PLO Mastermind foi verificada; não coletar base proprietária sem autorização.

## Controle
F1 parcial. Checkout completo, recuperação de snapshot, regressão integral, validação de bibliotecas externas, fontes estratégicas autorizadas e pendências históricas continuam abertas. F2 pode avançar nas tarefas não bloqueadas. Nenhuma alteração em main, deploy ou automação.
