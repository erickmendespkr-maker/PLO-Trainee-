# Ciclo 65 — revisão visual offline de intervalos entre mãos

## Escopo
Continua vigente `docs/VIDEO_ANALYZER_SCOPE.md`: somente análise assíncrona de gravações PLO5/PLO6, sem jogo ao vivo, mesas jogáveis, integração com salas ou apostas.

## Implementação
`activity_boundary_contact_sheet.py` reúne o plano de seeks `activity_boundary_seek_plan.py` e o manifesto de PNG/PTS decodificados por FFmpeg em um pacote offline de revisão com `index.html`, `report.json` e cópias dos PNG. As imagens são agrupadas por mesa e janela humana; os horários de seek solicitados e PTS decodificados aparecem separadamente. Quadros fora da janela candidata são sinalizados. Seeks sem quadro decodificado são listados explicitamente.

O módulo exige identidade SHA-256 da gravação, auditoria integral de hashes e PTS do manifesto, correspondência um-para-um dos seeks com as janelas, contagem consistente, caminhos relativos de PNG, limites de quantidade/tamanho, recusa sobrescrita e cópia de PNG com nova verificação de hash. Não calcula equity/EV nem declara transições, cartas, ações ou erros.

## Executar

```bash
python video_analyzer/activity_boundary_contact_sheet.py \
  seek_plan.json evidence_directory review_packet_directory
```

Abrir `review_packet_directory/index.html` localmente. `report.json` registra proveniência e ambiguidades; nenhuma decisão matemática é autorizada por este pacote.

## Testes e limites
- 17 novos testes unitários e de integração sintética com FFmpeg (4 mesas, 12 PNGs), incluindo adulteração de hash, seeks órfãos, tentativas de autorização indevida, limite de bytes e divergência de PTS.
- A suíte completa não deve ser declarada aprovada se ultrapassar o tempo limite.
- A revisão com vídeo real de 3–5 minutos continua bloqueada pela ausência de gravação autorizada. Não há validação de OCR real, precisão de limites ou processamento de 40–60 minutos.
