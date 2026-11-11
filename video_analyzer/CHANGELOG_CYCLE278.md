# Ciclo 278 — anotação humana e vínculo de evidências (11/11/2026)

## FEITO E TESTADO
- Reutilizado o vídeo PLO5 de 60min10s e a fila de 21 eventos provisórios gerada no ciclo 277; **nenhum vídeo, frame ou informação privada foi publicado**.
- Criado localmente o módulo `offline_review_queue_annotations.py`, que gera um template de anotação por evento (mesa, janela temporal, revisão, cartas, board, ação, pote e custo) e valida o JSON preenchido.
- Validação estrita de origem: SHA-256 do JSON da fila, SHA-256 declarado do vídeo, event_index e table_id; rejeita cartas duplicadas, quantidades incompatíveis PLO5/PLO6, timestamps inválidos, status indevidos e campos preenchidos sem revisão.
- O validador **não promove** revisões manuais a evidência matematicamente verificada: `hands_independently_verified=false` e `ready_for_equity_or_ev=false`, mesmo quando a anotação tem schema completo.
- **38/38 testes locais aprovados**: 13 novos casos para template/validação, 15 do handoff e 10 do probe FFmpeg/Tesseract.
- Aplicação real aos **21 eventos** do início da gravação: template gerado e validado em estado pendente, com `ready_for_equity_or_ev=false`.
- Arquivos e logs locais foram preservados no ambiente de execução. O módulo de anotação ainda precisa ser publicado no repositório; esta nota é o commit de progresso e não deve ser interpretada como entrega de código remoto.

## NÃO VERIFICADO
- Nenhuma das 21 alterações de OCR prova uma mão, decisão ou mudança exata de street.
- As 21 anotações continuam pendentes; não há mãos reais confirmadas, avaliação de equity/EV real, nem clipe MP4 com explicação estratégica verificada.
- Os testes foram executados localmente, sem CI remoto; não comprovam compatibilidade em Windows.

## PENDÊNCIAS MINHAS
- Publicar o módulo de anotação e seus testes, preservando equivalência com a versão local validada.
- Rotular visualmente 2–5 mãos com início/fim, cartas, ações, valores e confiança; o vídeo original já está disponível neste ambiente, mas não deve ser incluído no GitHub.

## PRÓXIMO CICLO
1. Publicar o módulo/testes de anotação no repositório.
2. Conferir as 21 janelas candidatas contra vídeo e medir falsos positivos de OCR.
3. Conectar mãos confirmadas a equity/EV condicionais, com limites de confiança e ranges explícitos.
4. Exportar cortes MP4 com explicações e hashes de proveniência.

Escopo: apenas processamento offline de gravações PLO5/PLO6; sem interfaces de jogo, RTA, acesso ao PLO Mastermind, custos ou alterações na main.
