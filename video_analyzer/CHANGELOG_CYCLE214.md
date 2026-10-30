# Ciclo 214 — linha do tempo offline de até quatro mesas

## Escopo e contrato

Adicionado \`offline_session_timeline.py\`, uma **visualização read-only** dos cortes revisados por humanos e dos resultados condicionais já existentes. Não lê plataformas de pôquer, não captura mesa ao vivo, não reconhece cartas e não calcula/avalia decisões. A fonte é a saída verificada de \`offline_reviewed_math_clip_gallery.assemble()\`; antes de publicar, também verifica que \`workspace/index.html\` continua byte a byte consistente com as entradas. O novo arquivo é \`workspace/timeline.html\`.

- Agrupa e ordena cortes por mesa e timestamp, com navegação por âncoras, faixa proporcional a 60 minutos e players MP4 com \`preload=none\`.
- Restringe a 1–4 mesas, 1–100 cortes (limite dos contratos atuais), timestamp até 3.600 segundos e proíbe sobreposição de mãos **na mesma mesa**. Sobreposição entre mesas é permitida.
- Mostra equity, intervalo de confiança **somente amostral**, status bloqueado e EV de showdown imediato **quando os dados já existem**. Não calcula nada novo.
- Faz escape de textos declarados pelo revisor, usa CSP sem scripts e recusa links simbólicos, sobrescrita e adulteração do HTML ao verificar.
- Inclui CLI \`--verify\` e saída JSON com \`recognition_verified=false\` e \`action_graded=false\`.

## Comandos

\`\`\`bash
cd video_analyzer
python offline_session_timeline.py PLAN.json ANNOTATIONS.json QUEUE.json WORKSPACE
python offline_session_timeline.py --verify PLAN.json ANNOTATIONS.json QUEUE.json WORKSPACE
python -m unittest -q test_offline_session_timeline
\`\`\`

## Testes

- 24 novos testes sintéticos: associação real com \`assemble\`, quatro mesas, 100 cortes, 60:00, overlap permitido entre mesas, overlap proibido na mesma mesa, XSS, hashes, dashboard adulterado, HTML adulterado, symlinks, timestamps não finitos e ausência de sobrescrita.
- 98 testes selecionados passaram na árvore local do ciclo (24 novos + 74 de regressão).
- Demonstração com sessão **sintética de 30 s e duas mesas**: geração e \`--verify\` da timeline passaram.
- Chromium: DOM com 2 mesas, 2 cortes e ausência de erros JS após \`set_content\`; \`file://\` bloqueado pela política do ambiente e MP4 **não reproduzido** nesse teste. Isso não valida Windows.

## Limites / próximos passos

- Ainda falta vídeo real autorizado e anotado de 3–5 minutos; não existe medição de precisão OCR/visão em gravações reais.
- Limite de 100 cortes por sessão é insuficiente para muitas sessões de quatro mesas e 60 minutos; ampliar contratos com paginação/batches antes de declarar suporte operacional completo.
- Não houve alteração de main, credenciais, produção, Actions ou custos. Nenhum teste comprova reconstrução automática de mãos, qualidade estratégica ou reprodução no Windows.
