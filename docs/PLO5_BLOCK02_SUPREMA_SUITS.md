# Bloco 02 — Perfil visual de naipes Suprema

Perfil offline PLO5, 1504×696, usa a mesma gravação Poker_Parte_01.mp4. Localização das cinco regiões Hero e cinco board, com recortes separados para valor e símbolo. Identifica o naipe por concordância de cores em ambas as regiões, contraste, fundo neutro e presença de máscara. Rejeita o fundo azul de mesa e candidatos ambíguos; posição vazia do Hero continua incerta. Nenhum valor de carta é emitido nesta etapa.

Calibração em cinco frames (850, 900, 950, 1000, 1100 s solicitados): 18/18 naipes visíveis, 32 posições sem carta sem falso positivo. Teste temporal em cinco novos frames (1150, 1250, 1350, 1450, 1550 s solicitados), sem ajuste de coordenadas/limiares após avaliação: 30/31 naipes corretos, 1 abstenção (primeira carta Hero, Jc, em 1450 s), zero erros aceitos, 18 posições sem carta sem falso positivo, 13/13 vazios do board corretamente indicados, 1 carta em animação rejeitada (excluída da contagem de cartas estáveis). A referência foi transcrita visualmente pelo assistente, sem revisão independente; os frames são da mesma sessão, mesa 4, sem auditoria independente de PTS. Outras posições foram testadas sinteticamente quanto à geometria, não em vídeos reais. Os frames de 1200, 1300, 1400, 1500, 1600 s examinados para verificar geometria não contam como holdout.

172 testes selecionados passaram no Linux (8 novos + 164 regressões, 4,674 s). CLI em frame real executada; SHA Git dos dois arquivos igual ao remoto. Dependências existentes: Pillow, plo5_fourcolor_cards.py, plo5_mixed_money.py. Nenhuma dependência externa nova.

Uso: python video_analyzer/plo5_suprema_suits.py FRAME.png

Entrega incremental concluída no escopo do bloco 02. Ainda não está ligada ao pipeline principal: bloco 03 deve calibrar os 13 valores específicos da Suprema, validar em amostra distinta e integrar ao leitor misto com cache. Não certifica cartas completas, mãos, resultados financeiros ou estratégia. Preservar demais pendências. Nenhuma gravação ou print privado publicado. Não alterar main.
