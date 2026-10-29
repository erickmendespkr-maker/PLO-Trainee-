# Ciclo 191 — revisão manual de cartas com timestamps por quadro

## Escopo
Somente análise offline de vídeos gravados PLO5/PLO6, conforme docs/VIDEO_ANALYZER_SCOPE.md. Não há captura ao vivo, mesas jogáveis, adversários IA, conexão com plataformas de poker, apostas ou gastos.

## Implementação
- Novo offline_manual_card_review_form.py: gera formulário HTML autocontido, sem requisições externas, a partir de selected_roi_clip_binding.json e clip.mp4 com SHA-256 validado. Nenhuma carta é inferida de OCR.
- Formulário oferece vídeo local, campos para 5/6 cartas privadas e 3–5 cartas do board, registro de video.currentTime por carta, notas e confirmação humana explícita, ranges uniformes ou combinações ponderadas, semente, iterações e parâmetros opcionais de EV de call.
- Exportação manual de JSON no navegador, com card_frame_evidence contendo {card, clip_timestamp_seconds}. Os timestamps são **alegações humanas**, não evidência automática de leitura correta.
- offline_reviewed_equity_clip_report.py aceita o campo opcional, valida cobertura, duplicações, tipo e finitude dos timestamps, e mantém compatibilidade com revisões anteriores.
- offline_equity_clip_explanation.py informa quantos quadros foram anotados e ressalta que não houve verificação independente.

## Testes executados localmente
- python -m unittest discover -p 'test_offline_*.py': **80 testes aprovados** no pacote local de 4 módulos, incluindo 20 novos de formulário/validação e 3 novos de apresentação.
- Playwright + Chromium headless com HTML carregado por set_content e MP4 sintético embutido em data URI: vídeo de 4 segundos, 11 cartas, timestamps, exportação JSON, equity condicional e explicação HTML: **PASS**. Nenhum erro JavaScript detectado.
- O navegador bloqueou navegação direta file:// (ERR_BLOCKED_BY_ADMINISTRATOR); por isso a interface foi testada com conteúdo embutido. Windows não verificado.
- O vídeo e as cartas digitadas são artificiais e não correspondem visualmente. A equity apenas valida a integração, não o reconhecimento nem a estratégia.

## Limitações e bloqueios
- Falta gravação real autorizada e anotada de 3–5 minutos para medir precisão de OCR, cartas/ações e reconstrução de mãos.
- Não há verificação independente de que a carta digitada estava visível no timestamp; nem identidade comprovada do jogador ou nota estratégica.
- Auditoria completa vídeo → frames → OCR não é reexecutada; vínculo anterior é validado por hash.
- Sessões 40–60 minutos, até 4 mesas, Windows, motor externo de equity, EV de raise e suíte integral pendentes.

## Como testar
1. python video_analyzer/offline_manual_card_review_form.py selected_roi_clip_binding.json clip.mp4 manual_review.html
2. Abra manual_review.html ao lado de clip.mp4, revise cartas e exporte JSON.
3. python video_analyzer/offline_reviewed_equity_clip_report.py selected_roi_clip_binding.json clip.mp4 manual_review_H4.json report.json
4. python video_analyzer/offline_equity_clip_explanation.py report.json clip.mp4 explanation.html

Não sobrescrever evidências. Não usar para assistência em tempo real.
