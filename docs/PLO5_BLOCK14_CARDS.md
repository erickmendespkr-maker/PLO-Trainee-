# Bloco 14 — candidatos de cartas PLO5 (25/11/2026)

## Entrega

video_analyzer/plo5_card_candidates.py lê os recortes vinculados ao job auditado do bloco 12. O OCR textual anterior exige rank e naipe em texto e aceita seis cartas; o novo caminho visual usa modelos de glifos de rank e naipe separados, exclusivamente cinco posições privadas e cinco comunitárias. Não modifica os módulos legados. Não adivinha naipe pela cor; usa distância de máscaras e margem entre as duas melhores correspondências, com limiares conservadores iniciais (distância <= 0,22, margem >= 0,08). Esses escores não são probabilidades calibradas.

CLI: python video_analyzer/plo5_card_candidates.py jobs.db JOB_ID profile.json templates new_report.json --max-gap 10

O perfil JSON exige variant=5, rank_roi e suit_roi (cada um [x,y,w,h] relativo à carta), e tables (um objeto por região auditada, table_id, hero e board; cinco retângulos [x,y,w,h] relativos ao recorte em cada campo). As dez regiões de carta não podem sobrepor-se; os glifos devem caber na carta e não sobrepor-se. Exemplo sintético de 240x160: rank_roi=[2,2,32,32], suit_roi=[2,34,32,32], hero=[[0,80,44,70],[48,80,44,70],[96,80,44,70],[144,80,44,70],[192,80,44,70]], board=[[0,0,44,70],[48,0,44,70],[96,0,44,70],[144,0,44,70],[192,0,44,70]]. NÃO calibrado para cliente real.

Templates: 17 PNGs rotulados rank_2.png a rank_9.png, rank_T.png, rank_J.png, rank_Q.png, rank_K.png, rank_A.png e suit_c.png, suit_d.png, suit_h.png, suit_s.png; glifo escuro em fundo claro, recortado do mesmo estilo de cartas, dimensões 8–256 px. T representa dez (o modelo visual deve refletir o glifo real). Não usar modelos sintéticos como calibração validada de uma sala real. Os hashes dos 17 modelos, perfil, manifesto e gravação são registrados. Os recortes são conferidos pelo hash antes de ler e o pacote é revalidado ao final.

Saída por frame: slots, candidatos individuais, distância/margem, proporção de pixels claros, cinco cartas privadas completas ou null, board contíguo de 0/3/4/5 cartas ou null, conflitos por duplicata. Board [] significa ausência visual de faces detectadas, não preflop comprovado. Cartas ilegíveis/ocultas não são inventadas. Mudanças de conjunto privado com dois frames distintos por lado, board visualmente vazio, mesma mesa e lacunas limitadas geram apenas intervalos de revisão; não são limites confirmados. Ordem diferente do mesmo conjunto não gera nova mão. O job continua review_required. Nenhum clipe ou EV/GTO autorizado.

## Testes

139 testes selecionados aprovados, 132 regressões e 7 novos, 20,575 s. Todos os 17 glifos sintéticos reconhecidos em seus modelos; testes de board 0/3/4/5, duplicatas, lacunas, carta oculta, glifo ambíguo, rejeição de variante 6, sobreposição, isolamento temporal. MP4 sintético H.264 de 2 s, 240x160, 5 fps, 3 recortes auditados: 24/24 leituras corretas (15 privadas, 9 comunitárias). Adulteração de recorte rejeitada. Os modelos e o vídeo usam o mesmo estilo artificial; não é avaliação independente de acurácia real. Regressões preservam o ambiente local do bloco 13, incluindo seus dois classificadores reproduzidos a partir do código consultado; não é a suíte integral do GitHub.

## Estado e pendências

Bloco 14 parcial: caminho de reconhecimento implementado/testado em fixtures, falta calibrar modelos e ROIs com gravação real de PLO5 e medir precisão/recall por carta, inclusive cartas parcialmente sobrepostas, fundos/naipes coloridos, layouts e compressão. A configuração de cinco posições não detecta uma sexta carta fora do ROI: pressupõe gravação PLO5 confirmada. Faltam identificação robusta da presença da mesa, fusão dos sinais de limites, refinamento temporal, validação de mãos completas e desempenho em sessão longa. Bloco 13 permanece parcial. Bloco 11B permanece pendente: dados GTO autorizados e execução do Poker-Eval. Nenhum vídeo real, template proprietário, main ou deploy alterado. Próximo bloco 15: posição, blinds, stacks, pote e sizing com evidência auditada.
