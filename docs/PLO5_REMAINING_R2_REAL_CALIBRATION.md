# R2 — calibração em gravações reais (26/11/2026)

As duas gravações recuperadas do Drive foram processadas localmente: Parte 01 (1618 s) e Parte 06 (1093,933333 s), 1504×696, total 45min11,933s. Nenhuma gravação ou imagem privada foi publicada no repositório.

## Entregas
- plo5_mixed_money.py: módulo independente de reconhecimento de candidatos monetários em frames gravados. Perfis PPPoker e Suprema para 1504×696, detecção por cor do feltro e barra de título, supressão de OCR em posições não reconhecidas, leitura de pote e stack em BB, SHA256 do frame. Ajuste de recortes estreitos para remover artefatos e guarda de separador decimal no stack PPPoker.
- O layout pode mudar durante uma sessão; Parte 01 também alterna para Suprema posteriormente, Parte 06 chega a ter posição fechada e painel de perfil.
- Uso: python video_analyzer/plo5_mixed_money.py frame.png [--platforms pppoker,pppoker,pppoker,suprema]. Por padrão detecta candidatos automaticamente. Somente análise offline de sessões encerradas.

## Validação
- Calibração: 12 frames (5, 25, 45, 65, 85, 105 s solicitados de cada vídeo), 96 campos: 95 numéricos, 1 ausente. Baseline: 58 acertos, 5 erros, 33 abstenções incorretas; ajustado: 96 acertos, 3,624 s.
- Verificação posterior de valores: 8 frames (125, 145, 165, 185 s de cada vídeo), 61 numéricos e 3 ausentes: 64 acertos, zero divergências, 2,404 s. Não usados no ajuste das ROIs, mas pertencem aos mesmos vídeos. Referências transcritas visualmente pelo assistente, não por revisor humano independente. Tempos de seek solicitados, sem auditoria independente de PTS.
- Layout: 28 frames, incluindo 8 mais tardios (Parte 01: 300, 600, 900, 1500 s; Parte 06: 300, 600, 900, 1050 s), 112 posições, 105 mesas visíveis e 7 sem mesa visível; 112 concordâncias. Os frames tardios foram usados no ajuste do detector, não são holdout de layout.
- 8 testes unitários aprovados; os 160 campos amostrados foram lidos com Tesseract real. Não é benchmark de sessão completa.

## Pendências preservadas
Módulo ainda não conectado ao pipeline principal, que usa outras geometrias. Recortes estreitos podem cortar valores mais longos. Reconhecimento automático das cinco cartas, board, posições, ações, limites de mãos, rebuys, resultados e validação externa continuam pendentes. Nenhuma mão completa reconstruída ou perda confirmada neste ciclo. Não é MVP nem garantia de precisão fora da amostra. Preservar R1–R4, F1–F5 e pendências históricas; sem novos blocos.
