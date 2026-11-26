# R2 — Reconhecimento e revisão financeira PLO5

## Alterações publicadas
- plo5_balance_review.py: prioriza candidatos de revisão por maior queda exibida de stack dentro de um segmento. Registra os dois prints de referência e aumentos de saldo subsequentes. O limite é estritamente superior a 30 BB por padrão. Queda exibida não é perda financeira.
- reconcile() aceita declarações explícitas de saldos inicial/final já liquidados, mesma mão e transferências completas. Confere âncoras com os valores candidatos e calcula saldo final - saldo inicial - rebuys + retiradas. Resultado condicional, sem validação independente do ledger de potes. Não identifica rebuys automaticamente.
- plo5_review_pipeline.py: inclui triage.json, quantidade de candidatos prioritários no manifesto, lista no HTML e tempo da etapa. Preserva a separação entre relatório estratégico e candidatos visuais.
- 30 testes locais aprovados, 11 novos (10 matemáticos/contratuais e 1 integração de relatório), 19 regressões. Fixtures de janelas e OCR simulado; nenhuma precisão em sessão real certificada. Exemplo sintético: stack 100→20→100→100; queda exibida 80 BB; resultado condicional 0 BB sem transferências, -80 BB com rebuy declarado de 80 BB. Sem declaração, resultado financeiro nulo.

## Recuperação de vídeos
Arquivo Gravar_2026_11_17_20_04_04_346.mp4 encontrado no Drive por ID conhecido. Metadados: 791630253 bytes. Download recusado com HTTP 413, limite 268435456 bytes. Busca de outros MP4 não retornou gravações utilizáveis. Clone GitHub direto no Linux segue falhando por DNS. Não houve acesso aos pixels dessa sessão.

## Pendências
R2 parcial. Teste real de três/quatro mesas, posição, identificação de Hero, cinco cartas, board, valores e ações de todos os jogadores, limites de mãos, potes paralelos, confirmação de pagamentos/rebuys, ledger integral e vinculação estratégica permanecem abertos. Para validação real neste ambiente, fornecer trechos de gravação original com mãos completas, mantendo resolução, abaixo de 250 MB cada. Preservar todas as pendências F1–F5 e históricas. Próximo disparo R3, sem ampliar escopo.
