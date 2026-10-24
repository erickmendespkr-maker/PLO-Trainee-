# Ciclo 77 — quadros FFmpeg para revisão matemática offline

## Entrega
- `activity_math_review_frames.py` transforma o handoff de revisão matemática em **imagens PNG de navegação** extraídas do vídeo original, sem autenticar cartas ou ações.
- Recalcula integralmente o handoff a partir da triagem, pacote e timeline originais; rejeita adulteração, permissões indevidas e SHA-256 divergente da gravação.
- Reutiliza um quadro para decisões de mesas distintas no mesmo timestamp; registra vínculo mesa/mão/evento, hash SHA-256 da imagem, orçamento e omissões.
- Exporta em pasta nova de forma atômica. Não sobrescreve resultados existentes. Rejeita links simbólicos nos arquivos de entrada.
- `test_activity_math_review_frames.py` verifica vídeo sintético com FFmpeg, quatro mesas, hash dos PNGs, CLI, imutabilidade, falhas de proveniência e limites.

## Como executar
Na pasta `video_analyzer`:

```bash
python activity_math_review_frames.py sessao.mp4 math_review_handoff.json math_triage.json hand_review_packet.json reviewed_timeline.json quadros_revisao --max-frames 40
python -m pytest -q test_activity_math_review_frames.py test_activity_math_review_handoff.py
```

A pasta gerada contém `math_review_frames.json` e `frame_XXXX.png`. Os timestamps em `requested_seek_pts_seconds` são **posições solicitadas ao FFmpeg**; o timestamp efetivo do quadro decodificado **não é medido** (`decoded_frame_pts_seconds: null`). São imagens de quadro completo, sem recorte de mesa validado.

## Limitações
- Não identifica cartas, potes, ações, início/fim das mãos ou erros estratégicos.
- Não calcula equity/EV nem gera MP4; todos os sinais de aprovação permanecem falsos.
- Demonstração e testes usam vídeo sintético; falta gravação autorizada de 3–5 minutos para benchmark de reconhecimento visual. Sessões reais de 40–60 minutos não foram validadas.
