# Ciclo 66 — pistas visuais quantitativas, offline e sem inferências de poker

Escopo: `docs/VIDEO_ANALYZER_SCOPE.md`. Nenhuma funcionalidade de jogo, adversário, sala online, apostas ou orientação em tempo real.

## Novo componente

`activity_visual_change_hints.py` consome o pacote local gerado por `activity_boundary_contact_sheet.py` (com `report.json` e PNGs em `images/table_XX/`). Revalida o SHA-256 de **cada** imagem, recusa symlinks, caminhos fora do padrão, contagens divergentes e alterações que autorizariam decisões automáticas. Decodifica cada PNG auditado com FFmpeg em uma amostra de luminância 48×48 e calcula diferença média absoluta normalizada entre quadros **adjacentes da mesma janela/mesa**, além de diferenças em três faixas horizontais. O JSON distingue PTS decodificados dos seeks solicitados, guarda hashes do relatório e gravação e mantém todas as decisões matemáticas bloqueadas.

O limiar `0.12` é uma referência **fixa de mudança de pixels**, não um detector calibrado de cartas, board, pote, início/fim de mão, erro ou confiança estatística. Animações, cursores e artefatos de compressão podem gerar diferença alta. Quadros sem decodificação, fora da janela ou com PTS não crescentes não produzem comparação; exigem revisão humana.

## Uso

```bash
python video_analyzer/activity_visual_change_hints.py \
  review_packet_directory visual_change_hints.json \
  --change-threshold 0.12
```

Para fixar a proveniência, usar `--expected-report-sha256 <sha256-canônico-do-report-json>`. A saída não sobrescreve arquivo existente. Exige FFmpeg disponível no PATH, sem dependência Python adicional.

## Testes

16 testes novos, todos com dados sintéticos, incluindo integridade dos PNG, diferença de pixels, PTS, múltiplas mesas, recusa de sobrescrita, proteção contra caminhos maliciosos e autorização indevida. Executar `python -m unittest -q test_activity_visual_change_hints`. Não confundir testes sintéticos com precisão medida em vídeo real.

## Limites

Falta vídeo autorizado de PLO5/PLO6 para aferir OCR e calibração das regiões do board/pote. Não há validação de precisão de reconhecimento, segmentação exata de mãos ou sessão real de 40–60 minutos. Este componente **não** produz ações nem permite cálculo de EV/equity.
