# Ciclo 58 — cartões matemáticos nos MP4 (23/10/2026)

## Escopo
Apenas análise offline/assíncrona de sessões PLO5/PLO6 gravadas. Não há assistência em tempo real, simulador de mesas, adversários de IA, integração com poker real ou execução de apostas.

## Mudanças
- video_analyzer/activity_math_clip_annotate.py: recebe manifesto de clipes humanos, diretório de MP4, worksheet, solicitação de ranges, relatório Monte Carlo e diretório de saída novo. Revalida a cadeia de proveniência, reexecuta o cálculo determinístico e acrescenta cartão explicativo separado de 8 s a cada MP4 via FFmpeg.
- Cartão distingue revisão humana, hipótese heads-up all-in, intervalo de confiança amostral e ausência de cálculo quando faltam parâmetros. Não autoriza ranking por EV nem diagnóstico de erros.
- Manifestos e sidecar JSON com hashes SHA-256 dos arquivos originais e derivados. Saída atômica em diretório novo; não sobrescreve os originais.
- video_analyzer/test_activity_math_clip_annotate.py: testes sintéticos de quatro mesas, decodificação de MP4, integridade, adulteração de relatórios/clipes, symlinks, entrada malformada, bloqueio de sobrescrita e CLI.

## Comando local
Na pasta video_analyzer:

    python activity_math_clip_annotate.py /caminho/review_clip_manifest.json /caminho/clips /caminho/worksheet.json /caminho/request.json /caminho/report.json /caminho/saida_nova

Requer ffmpeg, ffprobe e dependências locais do projeto. O diretório de saída não pode existir. O modelo matemático não é validado em gravações reais.

## Bloqueios
Falta vídeo PLO5/PLO6 autorizado de 3–5 min para validar OCR, reconstrução de mãos e posicionamento das mesas. O cartão matemático é apenas um what-if condicionado a ranges humanos, não EV real. A geração sintética não valida sessões de 40–60 min.
