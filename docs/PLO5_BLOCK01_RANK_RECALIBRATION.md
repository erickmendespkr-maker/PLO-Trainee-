# Bloco 01 — recalibração dos valores PPPoker

## Entrega
- Classificador PLO5 PPPoker 1504×696: limite de distância 0,34 e margem mínima 0,075, definidos a partir dos erros anteriores. Candidatos incertos são rejeitados.
- Novo CLI plo5_rank_recalibration.py reconstrói banco de máscaras a partir de anotações locais, em ordem temporal, com SHA-256 por frame, apenas partição train, sem cartas físicas duplicadas entre Hero e board. Banco reconstruído byte a byte igual ao banco final.
- Banco atualizado: 353 máscaras, versus 194 antes; 24 frames de desenvolvimento (5–565 s solicitados), incluindo seis frames anteriormente usados como holdout e seis frames de uma rodada intermediária. Banco e anotações locais entregues em ZIP, não publicados com imagens privadas.
- Primeira tentativa com 261 máscaras corrigiu os exemplos conhecidos, mas apresentou novo erro 4h→8h e menor cobertura nos seis frames intermediários. Esses frames foram então incorporados à calibração; não são evidência independente.

## Avaliação temporal final
Mesma gravação Poker_Parte_01.mp4, seis frames posteriores (605, 645, 685, 725, 765, 805 s solicitados), 116 cartas anotadas, 54 posições vazias, 34 campos Hero/board; labels transcritos visualmente pelo assistente. Nenhum desses seis frames usado na calibração. Mesma sessão, mãos podem repetir entre frames. Comparação verificada novamente com o classificador original e o atualizado, sem substituição da função de distância.

| Métrica | Anterior | Atual |
|---|---:|---:|
| Cartas corretas | 103/116 | 108/116 |
| Valores rejeitados | 13 | 8 |
| Cartas incorretas aceitas | 0 | 0 |
| Naipes corretos na região do símbolo | 116/116 | 116/116 |
| Campos completos corretos | 23/34 | 28/34 |
| Falsos positivos nas 54 posições vazias | 0 | 0 |

Nas amostras reaproveitadas de desenvolvimento (247 cartas) houve 241 corretas, 6 abstenções, zero erros aceitos, incluindo correção dos três casos Kh→Ah, 8h→9h e 9c→Qc documentados anteriormente. Não confundir ajuste nos dados de treino com generalização. 164 testes selecionados aprovados no Linux (6 novos, 158 regressões); não checkout integral. Nenhuma nova dependência externa necessária.

Uso com pipeline existente: python video_analyzer/plo5_review_pipeline.py mixed-video VIDEO.mp4 PASTA_NOVA --start 605 --seconds 20 --card-bank bank_final.json

## Estado
Entrega do bloco 01 (recalibração e comparação temporal) concluída no escopo incremental, não certificação da leitura de todas as cartas. Persistem abstenções, ausência de revisão humana independente, Suprema, posições, ações e reconstrução completa. Próximo bloco 02: calibrar regiões de Hero e board e naipes na Suprema, com a mesma gravação. Não baixar as quatro outras gravações apenas para desenvolvimento; não alterar main ou ampliar escopo.
