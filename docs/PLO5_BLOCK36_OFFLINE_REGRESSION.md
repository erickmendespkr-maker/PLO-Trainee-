# Bloco 36 — regressão offline PLO5 (25/11/2026)

## Entrega

video_analyzer/plo5_regression_runner.py consolida oito grupos explicitamente selecionados (35 módulos de teste, 328 IDs únicos). Executar a partir do repositório com Python, Pillow, FFmpeg, FFprobe e Tesseract instalados:

    python video_analyzer/plo5_regression_runner.py --equity-db CAMINHO/plo5_equity.sqlite --output novo_relatorio.json

Sem --group executa todos os grupos; --group pode ser repetido para executar subconjuntos. O modo padrão exige identidade de 81 arquivos da revisão base 7e6490bc27d8867182e121dc92490d16cddf09c5, conforme plo5_regression_baseline.txt. Para futuras alterações, --candidate registra todas as divergências de blobs sem barrar a execução por divergência; mantém a validação dos testes e do snapshot. O inventário é local e não constitui atestação de autenticidade externa. Exige SQLite revisado com SHA-256 bddf887d08b9bfaeb55ab55e287b3398c31cf51620dde2ce9986baf7aeddaa9a, dependências disponíveis, contagem esperada de testes, ausência de duplicatas, falhas de importação, erros, falhas, skips, expected failures e unexpected successes. Revalida os arquivos e o snapshot ao final. Relatório JSON registra ambiente, hashes, IDs, contagens e tempo por grupo; código de saída não zero em falha. Recusa sobrescrita. Não certifica MVP, sessão real ou GTO. Não exige rede nem GitHub Actions.

Recuperados localmente os arquivos integrais offline_real_video_probe.py e offline_board_street_proposals.py diretamente do GitHub. Blobs f97e22598131073ecff44029b42969bd163bda97 e b9d422d15b7673a10f972b2b64f582371b0c9911, respectivamente. Os 81 arquivos de código/testes/benchmarks preexistentes do ambiente local foram conferidos com os blobs do commit base; nenhuma divergência. Não houve alteração nos classificadores ou motores publicados, e as cópias parciais anteriores não fazem parte desta execução.

## Testes

328 testes distintos aprovados em oito grupos, executados por três invocações do runner, com os IDs conferidos também entre invocações: 8 contratos (2,031 s), 5 desempenho (3,565 s), 47 integração/relatórios (3,436 s), 78 estratégia (0,404 s), 93 matemática/financeiro/padrões (5,880 s), 47 ingestão/equity (17,861 s), 42 reconhecimento (16,619 s), 8 exportação (3,635 s). Tempo acumulado medido 53,433 s; zero falhas, erros ou skips nas baterias finais. Linux, Python 3.13.5, Pillow 12.3.0, SQLite 3.46.1. Não é a suíte integral do repositório: seleção dos módulos associados aos blocos 01–35, mais contratos do bloco 36. Testes compartilhados antigos mantidos sem ampliar o escopo de variantes.

Novos contratos: registro sintético de estratégia mista (fold 25%, call 50%, raise 25%) excluído do lookup de produção e dos relatórios; empate exato de EV entre call/raise não gera frequência; raise de 41 fichas acima do call não substituído por sizing de 40; board ausente retorna INSUFFICIENT_DATA e não apresenta cálculo como análise da jogada; sensibilidade entre hipóteses não certifica leak; pacote MP4 sintético de duas mesas com quatro decisões declaradas (uma NO_MATCH, uma INSUFFICIENT_DATA e duas MISSING_REPORT) mantém zero comparáveis, um corte explicitamente revisado e pixels auditados; executor rejeita skip sentinela, duplicatas e contagem divergente; snapshot inválido rejeitado e inventário conferido. Não valida mãos reais reconhecidas automaticamente.

## Estado

Bloco 36 concluído no escopo da suíte selecionada de regressão e integração offline. Ações/limites de mãos reais, OCR, referência GTO, validação de sessão completa, compatibilidade Windows e instalação final ainda não certificados. Preservar pendências 11B, 13–19, 24, 27, 28, 32, 33, 34 e 35. Próximo bloco 37: mãos reais anotadas, referência humana e métricas de precisão/cobertura. Nenhuma mudança em main, deploy, automação ou dados privados.
