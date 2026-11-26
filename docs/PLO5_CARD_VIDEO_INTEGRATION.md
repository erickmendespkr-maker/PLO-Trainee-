# Bloco 1 — integração das cartas e agrupamento temporal (26/11/2026)

## Entrega
- plo5_fourcolor_cards.observe aceita leitor de slot opcional; comportamento padrão preservado.
- plo5_card_review.py: cache por bytes RGB exatos de todas as regiões utilizadas no reconhecimento de cada carta, específico por campo; agrupamento de observações consecutivas com cinco cartas distintas do Hero, board legal, sem colisões, mesmo Hero e extensão do board. Interrompe grupo em incerteza, lacuna, mudança de plataforma, reset do board ou mudança de cartas. Não comprova identidade da mão.
- plo5_mixed_review.py: opção --card-bank, usa a mesma extração de frames para cartas e valores, verifica SHA256 do banco, registra candidatos e grupos no manifesto e no HTML. Nenhuma mudança no caminho padrão sem banco.
- Uso: python video_analyzer/plo5_review_pipeline.py mixed-video VIDEO.mp4 PASTA_NOVA --start 245 --seconds 20 --card-bank bank.json

## Execução real
Somente Poker_Parte_01.mp4, 245–265 s, 20 frames disponíveis, 80 posições, 60 posições PPPoker e 20 não reconhecidas pelo detector. 600 slots examinados: 401 cartas candidatas, 171 vazios candidatos, 28 incertos. 38 grupos Hero completos e 53 boards completos (inclui vazios), 31 observações com ambos; agrupados em 5 segmentos candidatos, sem confirmação de mãos completas. Não são contagens de acerto. Tempo total 6,232 s; reconhecimento das cartas 0,941 s incluído no tempo total. 
Comparação isolada das cartas nos mesmos 20 frames: sem cache 4,414 s; com cache 0,996 s; 4,43x; 464/600 slots reutilizados (77,33%). Todos os resultados idênticos ao fluxo real. Uma execução por configuração. Não representa benchmark de sessão nem precisão.
158 testes locais selecionados aprovados em 4,516 s (8 novos, 150 regressões); suite recuperada, não checkout integral. Quatro blobs de código/teste conferidos com arquivos locais. Banco de máscaras anterior mantido, sem ajuste nos limiares; três erros de valor anteriormente documentados permanecem pendentes. Não houve nova medição de acurácia, nem nova integração externa. Nenhum vídeo/print privado publicado.

## Pendências
Acurácia de valores, perfil Suprema, identificação de Hero/posições/ações, confirmação temporal de mãos completas, pagamentos, rebuys, rake e potes paralelos, análise estratégica vinculada, desempenho em sessão completa, database e validação Windows continuam abertas. Apenas uma gravação usada para desenvolvimento; segunda reservada para validação se necessária. Nenhum custo, alteração em main ou ampliação de escopo.