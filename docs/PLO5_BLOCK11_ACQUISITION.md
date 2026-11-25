# Bloco 11 — PLO5: aquisição e avaliação técnica (25/11/2026)

## Dados realmente importados

Fonte: https://solvepoker.app/plo5-starting-hand-rankings — SolvePoker (solvepoker.app), CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/). CSV entregue pelo usuário, versão indicada no cabeçalho 2026-05-04T20:22:06.261Z. SHA-256: 5a636b991a836da6b01b5802f97b7b5bd1479a0dc2bda2482422efa0d3d94651.

Executar localmente: python video_analyzer/plo5_equity_store.py plo5-hand-rankings.csv plo5_equity.sqlite

Importação completa local: 134459 linhas, 2598960 combinações, 28496 descrições distintas de rank/naipes. SQLite 8409088 bytes, SHA-256 bddf887d08b9bfaeb55ab55e287b3398c31cf51620dde2ce9986baf7aeddaa9a. Comparação campo a campo com CSV: 134459 linhas iguais; integrity_check ok. CSV original e SQLite não foram enviados ao GitHub; a base local foi entregue ao usuário. Metadados preservam licença, atribuição, comentários, versão e transformação. Importador exige hash da versão revisada; atualização futura requer revisão explícita. Consulta por descrição retorna todas as linhas e envelope dos bins; não há mapeamento exato de naipes. Dados de equity contra um adversário aleatório, não GTO, não EV por ação nem frequências.

Testes locais: 84/84 aprovados (78 regressões + 6 novos). Sem testes de vídeo real ou integração ao pipeline neste bloco.

## Estratégia GTO: acesso autorizado pendente

- PLO Spot: https://plospot.com/data-and-method.html — soluções Monker pré-flop, árvore padrão 6-max 100 BB de 1324 nós; não publica medidas de convergência. Contato divulgado: jh.iskra@gmail.com. Solicitar licença explícita, exportação oficial, escopo de uso offline, distribuição e metadados de modelo. Não coletar sistematicamente.
- SolvePoker: https://solvepoker.app/faq e https://solvepoker.app/docs — Notebook oferece consultas e exportações CSV/JSON, mas não há API pública. Contato divulgado: cs@solveplo.app. Solicitar autorização específica para reutilizar estratégias, não confundir com CC BY 4.0 do CSV de equity. Nenhum contato enviado, conta criada ou material proprietário importado.
- Registros GTO efetivamente importados: 0.

## Poker-Eval — avaliação estática, integração NÃO aprovada

https://github.com/jejellyroll-fr/poker-eval, master consultado. README blob d8d664e3f12626ac2397e15cca6bcd7cacac3e4e; LICENSE blob a4fc708235b14b7b465a095e8f5b331ee579c8ab (BSD-3-Clause); LICENCE blob 58e433d990cb6b3f11810d37e0fd83070590d2c5 (registro histórico GPLv3+). CMakeLists.txt blob 6fb85cb2db1be9554d5c7832d5d546ec6c5ed2ae, versão declarada 1.3.3. Necessário revisar licença por componente antes de distribuir. Não incorporar código agora.

Exemplos: examples/plo_hu_streets/README.md blob 66a5e6d448ca6b4036fb8a94f6b04f0513700d7f. Árvore HU 100 BB, quatro streets, 30 nós/20 decisões, ações simplificadas. Ferramentas anunciadas: mpf_run_with_metrics e mpf_dump_results (JSON/CSV). Não prova capacidade 6-max. Clone remoto falhou por DNS (Could not resolve host: github.com); build e execução não realizados.

Próxima validação, quando houver cópia autorizada do código: fixar commit, revisar licença e dependências, compilar CPU-only com CMake, executar ctest e oráculo independente PLO5; rodar árvore HU limitada, validar legalidade das ações, normalização de frequências, unidade de EV, ranges e blockers, tempo/memória, métricas de convergência e qualidade. Não promover a saída a GTO sem evidência. Nunca extrapolar HU a 6-max.

## Estado

11A (importação de equity): concluído localmente. 11B (investigação e avaliação estática): realizada; permissão para dados estratégicos e teste executável do solver pendentes. Sem alteração em main, deploy ou serviços pagos. Próximos blocos de vídeo podem avançar independentemente, preservando pendências de GTO.
