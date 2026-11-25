# Bloco 19 — Reconciliação financeira PLO5 (25/11/2026)

## Entrega

video_analyzer/plo5_financial_reconcile.py recebe o job auditado do bloco 12, rascunhos do bloco 17, relatório de rótulos de resultado do bloco 18 e uma revisão explícita de lançamentos incrementais do Hero. O CLI verifica identidade, cobertura dos recortes nos rascunhos, PTS, SHA, mesa e assento declarado, além da integridade do pacote e dos arquivos antes/depois. O relatório de resultados é vinculado pelo hash e identidade; seus episódios NÃO são convertidos automaticamente em lançamentos nem autenticados como pagamentos. A transcrição do revisor também não é autenticada como verdade visual. Nenhum resultado financeiro verificado ou corte automático é autorizado.

CLI: python video_analyzer/plo5_financial_reconcile.py jobs.db JOB_ID drafts.json results.json review.json new_report.json

review.json exige variant=5, job_id, draft_sha256, result_sha256 (SHA-256 dos respectivos arquivos) e reviews, lista com até uma entrada por draft_id. Cada entrada contém draft_id, hero_seat, complete (booleano; declaração de que a janela abrange a mão inteira e todos os lançamentos), reviewer, before e after (cada um {file,bb} ou null), events (lista de {file,kind,bb}). Valores em BB explicitamente transcritos como strings decimais não negativas com ponto, até 9 dígitos inteiros e 6 decimais; não converter fichas sem referência. Âncoras devem ser anteriores/posteriores a todos os lançamentos, no mesmo segmento, antes de qualquer contribuição e depois de todas as premiações/ajustes da janela. Eventos positivos estritamente ordenados por PTS; um por quadro, para impedir dupla contagem evidente e ordem ambígua. Não é possível representar dois lançamentos distintos no mesmo PTS neste formato; requer evidência temporal adicional. Não transcrever sizing de raise como contribuição incremental sem validação.

Tipos: contribution (inclui blind/ante efetivamente investido), return (devolução não disputada), payout (premiação líquida de rake creditada, inclui pagamentos principal/laterais distintos), rebuy (entrada externa), withdrawal (saída externa). Não descontar rake duas vezes. Não calcular side pots nem inferir o vencedor a partir dos valores; esse trabalho permanece no bloco 18.

A = contribuições; D = devoluções; G = premiações; X = rebuys - retiradas. Resultado condicional = G+D-A. Saldo esperado = inicial+X+resultado; resíduo = observado - esperado. Decimal, igualdade exata na precisão declarada. Saldo intermediário negativo, devoluções acima das contribuições, resíduo não nulo, revisão incompleta ou âncoras ausentes bloqueiam resultado e filtro; lançamentos apresentados são totais submetidos, não fatos financeiros. Exige declaração de completude, não prova que não faltam eventos. Perda estritamente superior a 30 BB quando net < -30, apenas sob dados reconciliados declarados. EV loss null; nenhuma afirmação de erro estratégico, GTO ou variância.

## Testes executados

175 testes distintos selecionados aprovados em quatro execuções: 8 novos (0,001 s), 78 estratégicos (0,503 s), 47 ingestão/equity (17,814 s), 42 reconhecedores (16,060 s). Todos retornaram OK. Regressões incluem fixtures MP4 anteriores; os oito testes novos são de reconciliação e fusão estrutural sintéticas, não teste ponta a ponta do novo CLI com vídeo real. Mantém ambiente de regressão do bloco 18, incluindo dois classificadores reproduzidos localmente no bloco 13. Não é a suíte integral do GitHub. Dependências PLO5 hand drafts, result candidates e ingest job conferidas contra os blobs remotos anteriores.

Casos: fold -45 BB; exatamente -30 excluído; -30,000001 incluído; perda -80 com rebuy +100 e retirada -10; contribuição 60, devolução 5, premiações 80+20, rebuy 100 => ganho +45 e saldo 245 desde 100; divergência, saldo ausente, devolução excessiva, saldo intermediário impossível, duplicata de PTS, unidades inválidas, origem/assento incompatíveis e revisões repetidas.

## Estado

Bloco 19 parcial: motor contábil condicional e vinculação estrutural implementados/testados. Não automatiza a transcrição dos lançamentos; rascunhos e episódios OCR não bastam para confirmar valores. Faltam janela completa real, contribuições incrementais, ordenação, pagamentos/side pots/rebuys reais, tolerância explícita para arredondamento de sala e teste ponta a ponta do CLI. Preservar pendências 11B e 13–18. Próximo bloco 20: validar avaliador exclusivamente PLO5, exatamente duas cartas privadas e três comunitárias, com oráculos independentes e benchmarks. Sem alterações em main, deploy, automação ou dados privados.
