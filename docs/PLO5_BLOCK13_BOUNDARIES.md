# Bloco 13 — presença de mesas e candidatos a limites (PLO5)

## Entrega parcial verificável

O módulo video_analyzer/plo5_boundary_candidates.py reutiliza classify de offline_real_video_probe.py e sample_board de offline_board_street_proposals.py. Consome os recortes auditados do bloco 12; não decodifica novamente o vídeo nem cria outro motor. Vincula o relatório à variante 5, job, SHA do vídeo, manifesto e calibração. Revalida o pacote no fim. Não modifica o estado review_required.

CLI: python video_analyzer/plo5_boundary_candidates.py jobs.db JOB_ID calibration.json new_report.json --max-gap 10

Calibração de exemplo para o fixture de 64x64 (NÃO calibrada para sessão real):
{"felt_rgb":[20,100,40],"tolerance":30,"board_strip":{"offset_x":8,"offset_y":5,"step_x":10,"width":8,"height":10,"white_min_rgb":200,"min_white_fraction":0.8}}

Por mesa, duas observações distintas de board visível seguidas de duas observações de board sem faces brancas produzem um intervalo candidato de reset, com quatro referências a recortes. Observações ambíguas, ausência de mesa e lacuna superior ao limite interrompem a sequência. PTS duplicados não contam como observações adicionais. Um intervalo candidato não é um limite confirmado, nem autoriza clipe ou análise matemática.

## Testes

132 testes selecionados aprovados localmente, 125 regressões e 7 novos (18,998 s). Seis sequências negativas sintéticas produziram zero candidatos; uma sequência positiva sintética produziu um candidato; isolamento entre quatro mesas simulado. Fixture MP4 real decodificado por FFmpeg, com uma região de felt, gerou três observações e nenhum candidato; adulteração do recorte rejeitada. As duas funções de classificação e seus auxiliares efetivamente chamados foram reproduzidos localmente a partir do texto do GitHub (blobs f97e22598131073ecff44029b42969bd163bda97 e b9d422d15b7673a10f972b2b64f582371b0c9911). Download integral desses dois módulos falhou por DNS; não executada a suíte integral dos módulos de origem. Os novos arquivos são testados localmente e publicados, com verificação de hash. Não houve vídeo de poker real nem medição de acurácia em jogo.

## Pendências

A localização livre de retângulos ainda não está implementada; presença é proposta em regiões previamente configuradas. O classificador usa sinais visuais e pode confundir sobreposições ou mudanças de tema com cartas/mesa. Não identifica mãos que terminam antes do flop, folds, cartas privadas, dealer, ações nem limites exatos. O amostrador do bloco 12 é esparso (30 s padrão) e tem teto de 512 recortes; com max-gap padrão 10 s, muitas transições não são avaliáveis. Refinamento temporal adaptativo e validação contra anotações humanas são necessários antes de considerar o bloco 13 integralmente concluído. Não extrapolar seis casos negativos para taxa de falsos positivos de vídeos reais.

Bloco 11B permanece pendente (licenças GTO e validação executável do Poker-Eval). Nenhuma alteração em main, deploy, automação ou dados proprietários.
