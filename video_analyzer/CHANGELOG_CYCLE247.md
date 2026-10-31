# PLO Trainee — Ciclo 247 (2026-10-31)

## Escopo
Somente vídeos gravados de PLO5/PLO6 offline/assíncronos, até quatro mesas. Sem mesas jogáveis, adversários de IA, integração com poker real ou assistência ao vivo.

## Implementação
- `offline_street_evidence.py`: recebe observações não verificadas por timestamp e as organiza por mesa, mão e street (preflop/flop/turn/river), com proveniência `ocr_proposal` ou `manual_claim`. **Não realiza OCR** nem infere cartas ocultas.
- Valida SHA-256 do vídeo, duração via FFprobe, timestamps monotônicos, ordem das streets, máximo de quatro mesas, quantidade de cartas privadas PLO5/PLO6 e comprimento do board por street.
- Contradições entre propostas de board/cartas privadas são sinalizadas para revisão, nunca promovidas automaticamente a fatos.
- Exporta JSON estruturado e HTML offline escapado, preservando confiança declarada **não calibrada**, bloqueio explícito de autorização matemática automática e revisão humana obrigatória.
- Publicação com arquivos temporários e rollback em falhas.
- `test_offline_street_evidence.py`: 20 testes sintéticos cobrindo PLO5/PLO6, integridade, conflitos, HTML, segurança, timestamps e rollback.

## Uso
```bash
python video_analyzer/offline_street_evidence.py VIDEO.mp4 OBSERVATIONS.json OUTPUT_DIR
cd video_analyzer
python -m unittest -v test_offline_street_evidence.StreetEvidenceTests
```

## Contrato de entrada (resumo)
```json
{
  "schema_version": 1,
  "status": "offline_unverified_street_observations",
  "source_video_sha256": "<sha256 do vídeo>",
  "variant": "PLO5",
  "hands": [{
    "table_id": "T1", "hand_id": "H1", "start_seconds": 0.2,
    "end_seconds": 3.8,
    "events": [{
      "timestamp_seconds": 0.4, "street": "preflop",
      "kind": "hero_cards", "value": ["AS","KH","QD","JC","TS"],
      "origin": "ocr_proposal", "confidence": 0.55
    }]
  }]
}
```

## Verificado
20 testes novos aprovados em diretório independente com FFmpeg/FFprobe; demonstração sintética de quatro mesas e um conflito de board sinalizado. Código e testes publicados na branch `feature/plo5-plo6-training`. A suíte integral do repositório não foi executada.

## Não verificado / bloqueios
Sem vídeo real autorizado e anotado de 3–5 minutos, sem medição de precisão OCR, sem processamento real de 40–60 minutos e sem teste Windows. O novo ledger ainda não se conecta automaticamente ao relatório de clipes temporais nem autoriza equity/EV.