# Bloco 15 — candidatos financeiros e posicionais PLO5 (25/11/2026)

## Entrega

O módulo video_analyzer/plo5_context_candidates.py consome recortes auditados do bloco 12, reutiliza o parser TSV existente de ocr_probe e valida retângulos com box/overlap do bloco 14. Preserva o texto OCR, a confiança não calibrada, a região e o SHA-256 dos bytes RGB da região; vincula o relatório a job, manifesto, perfil, arquivo do recorte e PTS. Revalida a integridade antes e depois do processamento. O estado do job não muda e o relatório não autoriza EV, reconstrução ou cortes automáticos.

CLI: python video_analyzer/plo5_context_candidates.py jobs.db JOB_ID profile.json new_report.json --threshold 0.75 --max-tasks 1024

O perfil exige variant=5 e tables, uma entrada por região auditada. Cada mesa declara table_id, hero_seat, pot, blinds e seats (2–6 assentos efetivamente participantes da mão, em ordem horária, como hipótese de calibração). Cada assento declara seat, stack, bet e dealer. As regiões são [x,y,width,height] relativas ao recorte, sem sobreposição. Exemplo exclusivamente sintético (640x240):
{"variant":5,"tables":[{"table_id":1,"hero_seat":1,"pot":[0,0,180,50],"blinds":[200,0,200,50],"seats":[{"seat":1,"stack":[0,60,180,50],"bet":[200,60,180,50],"dealer":[400,60,80,50]},{"seat":2,"stack":[0,120,180,50],"bet":[200,120,180,50],"dealer":[400,120,80,50]}]}]}

Valores aceitos: número não negativo, até 9 dígitos inteiros e 2 decimais, com unidade explícita BB/chips/fichas. Blinds exigem SB/BB com unidade comum, 0<SB<BB; quando expressos em BB, BB=1. Não inferir unidade, valor de região vazia ou separador ambíguo. Decimal preserva valores; conversão de fichas depende do BB em fichas e é arredondada a seis casas decimais em BB. Valores monetários em reais e símbolos de outras moedas não suportados por este parser.

Posição candidata depende de um único marcador OCR D ou BTN acima do limiar e demais ROIs de dealer visualmente uniformes (amplitude de luminância <=12, heurística inicial). Qualquer ROI concorrente não uniforme e não reconhecida bloqueia posições. A heurística não comprova ausência de marcador. Heads-up: BTN/SB e BB; 3–6 jogadores, posições condicionadas à ordem declarada. Não detecta assentos vazios, sit-outs, dead button, straddle, folds ou quem está efetivamente na mão. Saldo efetivo restante por adversário = mínimo dos dois saldos restantes normalizados; não é stack efetivo inicial ou valor all-in a pagar. Valor exibido da aposta não é necessariamente contribuição acumulada nem sizing de raise. Stack inicial, amount_to_call e rake permanecem null.

## Testes locais

146 testes selecionados passaram, 7 novos e 139 regressões, em 22,587 s. Python 3.13.5, Tesseract 5.5.0. ocr_probe.py e table_regions.py recuperados do GitHub, hashes locais correspondentes aos blobs fce77a2d9a679777a3545bc1b2ad74edfa28c157 e 78f732ba0f2db15664a0df7120805d61d171556f. A suíte ainda contém os dois classificadores reproduzidos no bloco 13 (ver documentação daquele bloco), não é a suíte completa do repositório.

MP4 sintético H.264 de 2 s, 640x240, 5 fps: 3 quadros, 24 tarefas de ROI (21 chamadas Tesseract e 3 ROIs uniformes dispensadas), pot 10 BB, blinds 0,5/1 BB, stacks 120/70 BB, apostas 3/1 BB, BTN/SB e BB; stack efetivo restante 70 BB nos três quadros. Primeira execução identificou OCR espúrio em ROI vazia; o tratamento de uniformidade corrigiu o fixture. Testes de unidades, conversão, posições de 2–6 assentos, dealer duplicado, valores ausentes, região inválida, exclusão de PLO6, orçamento e adulteração aprovados. Dados sintéticos não medem precisão em jogo real.

## Estado

Bloco 15 parcial: implementação funcional em fixture, pendentes calibração e validação em sessões reais, detecção automática de ocupação e dealer gráfico, stacks efetivos iniciais e sizing por histórico de ações. O teto de 1024 tarefas por padrão (máximo 4096) bloqueia jobs maiores; falta processamento em lotes integrados e medição de desempenho em sessão completa. Preservar blocos 11B (dados GTO autorizados e execução Poker-Eval), 13 e 14 (limites, detecção e calibração real). Próximo bloco 16: reconhecimento de ações/folds e evidência temporal. Sem alterações em main, deploy ou automação.
