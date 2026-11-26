# Bloco 1 — calibração PPPoker com quatro cores

Utilizada uma única gravação, Poker_Parte_01.mp4, conforme orientação do usuário. Perfil de 1504×696. Cor dos naipes: paus verde (c), copas vermelho (h), espadas preto (s), ouros azul (d). Valor reconhecido por máscara de caractere com proporção geométrica e margem de distância. Cor medida separadamente nas regiões do valor e do símbolo; desacordo ou baixa margem causa abstenção. Candidatos de hero/board exigem contagem legal e cartas distintas; colisões entre grupos rejeitadas. Suprema e outros layouts não abrangidos.

## Evidências
12 frames de calibração/desenvolvimento, 5–225 s solicitados. Banco de 194 máscaras distribuídas pelos 13 valores. Seis frames de teste posteriores, 245–345 s solicitados, com parâmetros congelados antes da avaliação. Mesma sessão, algumas mãos repetidas, referência transcrita visualmente pelo assistente, sem revisor independente ou auditoria de PTS. 
- 124/124 naipes corretos na região do símbolo.
- 116/124 cartas completas corretas, 5 abstenções e 3 erros de valor (93,55% de acertos considerando abstenções). Erros Kh→Ah, 8h→9h, 9c→Qc.
- 56 posições vazias anotadas, sem falso positivo de carta.
- 28/36 grupos hero/board completos corretos, 3 errados, 5 incompletos.
- 8 testes novos e 16 regressões selecionadas aprovados no Linux (24/24, 0,098 s). Reprodução da calibração e métricas confirmada por hash dos frames locais. CLI real de frame testada.
- Módulo e testes publicados, hashes locais/remotos conferidos. Banco local de máscaras e métricas entregue em ZIP incremental, sem gravação nem prints privados. Não foi necessário importar projeto adicional para a classificação por cores; Pillow e perfil existente bastaram. Nenhuma certificação de precisão de sessão, mão ou GTO.

Uso: python video_analyzer/plo5_fourcolor_cards.py FRAME.png bank.json

## Pendências
Corrigir confusões de valores, calibrar Suprema e outros layouts, validar cartas com novos trechos, otimizar cache, integrar candidatos ao pipeline de vídeo sem promover leituras não verificadas a estratégia. Reconstrução de mãos, ações, posições, resultado financeiro e demais pendências permanecem abertas. Não baixar as outras quatro gravações apenas para calibração; usar a segunda já recuperada na validação final quando necessário. Não alterar main ou ampliar escopo.