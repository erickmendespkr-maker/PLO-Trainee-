# PLO Trainee — Ciclo 95 (25/10/2026)

## Escopo
Somente `feature/plo5-plo6-training`; análise **offline e assíncrona** de gravações PLO5/PLO6. Sem mesas jogáveis, agentes de jogo, captura em tempo real, integração com plataformas de poker, credenciais ou gastos.

## Implementação
- `hand_math_intake.py`: converte o histórico de anotações e vereditos visuais do Ciclo 94 em formulários **vazios** de preparação para revisão matemática, separados por mesa e intervalo.
- Exige relatório `visual_verdicts_linked_to_unverified_hand_history_no_math`, hashes de procedência, flags de autoridade `false`, identificadores únicos, timestamps finitos e contagens consistentes. Não autentica o conteúdo visual do vídeo original.
- Preserva os vereditos por campo/ação como **referências**, sem copiar valores alegados para as entradas matemáticas. Mesmo `confirmed_visual` permanece bloqueado até atestação independente da mão e da decisão.
- Exige que um humano forneça separadamente cartas, board, ação, pote, valor para pagar, confiança por campo, ranges adversários e parâmetros do modelo. **Não executa** Monte Carlo ou EV; não produz um manifesto aceito diretamente pelo motor matemático.
- A saída JSON é criada sem sobrescrever arquivos; registra SHA-256 do histórico de origem e os bloqueios de cada intervalo.

## Execução
```bash
cd video_analyzer
python hand_math_intake.py history_with_visual_verdicts.json manual_math_intake.json
python -m unittest -q test_hand_math_intake test_decision_evidence_gate test_range_ev
```

## Testes e evidências
- **17 testes novos aprovados** em `test_hand_math_intake.py` (dados sintéticos, 4 mesas, falsificação de flags/contagens, timestamps, hashes, duplicação, saída imutável, symlink, NaN).
- **37 testes selecionados aprovados**, incluindo os 17 novos, `test_decision_evidence_gate` e `test_range_ev`.
- Demonstração com `history_linked.json` sintético do Ciclo 94: **4 intervalos**, **24 referências de anotação**, **0 prontos para matemática**.
- Uma execução de regressão mais ampla excedeu o tempo disponível; **não declarar aprovação** dessa seleção nem da suíte completa.

## Bloqueios
- Falta vídeo autorizado de 3–5 minutos e anotações humanas de referência para avaliar reconhecimento real.
- OCR real, sessões de 40–60 minutos e pipeline ponta a ponta equity/EV → seleção → clipes MP4 não validados.
- Formulário de intake não substitui reauditoria das imagens nem revisão humana independente. Nenhum cálculo matemático foi autorizado por este módulo.

## Próximo ciclo
Conectar a entrada manual preenchida à validação independente de cartas, ações, valores e ranges, com rastreabilidade do vídeo original e sem inferir dados escondidos.
