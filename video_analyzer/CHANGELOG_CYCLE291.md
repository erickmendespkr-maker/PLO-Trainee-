# Ciclo 291 — 12/11/2026 — Gate de revisão por campo

## FEITO E TESTADO
- Consultados os documentos de escopo e referência técnica e o HEAD inicial da branch: `0b85bab4593652885b70df3ba73eca9398ba6293`.
- Implementado `offline_review_decision_gate.py`: aceita apenas registros de revisão offline PLO5/PLO6, mesas 1–4, timestamps e SHA-256, cartas visíveis, evidências por campo com status, confiança e timestamp.
- OCR candidato, campos desconhecidos, cartas privadas não visíveis, board insuficiente, ação desconhecida, ausência de custo de call ou ranges não fornecidos produzem `INSUFFICIENT_DATA`; não são promovidos a fatos.
- O status `READY_FOR_CONDITIONAL_MODEL` permite somente uma próxima análise **condicionada a ranges**, não significa mão integralmente reconstruída nem diagnóstico correto/errado. `source_hand_reconstruction_verified`, `strategic_error_established` e `gto_solution` permanecem falsos.
- Executados localmente **16/16 testes sintéticos**, incluindo PLO5/PLO6, duplicatas, intervalos, tipos booleanos indevidos, OCR não confirmado e ranges ausentes.
- Publicados módulo e testes, com confirmação por hash Git de que os bytes publicados correspondem aos testados. Somente branch autorizada; nenhuma gravação privada publicada.

## NÃO VERIFICADO
- Sem checkout Git local por falha DNS ao acessar github.com; testes não foram executados dentro de um checkout integral, nem CI remoto.
- Os testes anteriores pendentes (15 do ciclo 287 e 10 do ciclo 289) permanecem sem validação nesta execução.
- O ambiente local continha somente dois MP4s demonstrativos anteriores, não o RAR original PLO5. Nenhuma mão real foi revista, nenhum OCR de gravação real foi medido e nenhum MP4 novo foi exportado.
- O gate é triagem estrutural; não prova que o humano identificou corretamente a mão. Não existe integração ponta a ponta com o motor de equity neste ciclo.

## PENDÊNCIAS MINHAS
- Reexecutar suítes pendentes e regressões em checkout completo.
- Criar histórico de evidências com correções humanas auditáveis, vínculos entre quadros e decisões, e ligação ao motor de equity/EV sem confundir hipóteses com observações.
- Recuperar acesso autorizado ao vídeo original e construir benchmark manual de 2–5 mãos.

## PRÓXIMO CICLO
- Integrar gate de revisão ao cálculo condicionado, preservando `INSUFFICIENT_DATA` e sem promover campos incompletos a `source_hand_reconstruction_verified`.
- Testar exportação de clipes sintéticos com auditoria PTS/FFprobe e sidecars SHA.
- Medir reconhecimento de cartas, ações e potes somente quando existirem anotações humanas da gravação.

Executar testes novos: `cd video_analyzer && python -m unittest -v test_offline_review_decision_gate`.

PLO Mastermind usado somente como referência conceitual. Sem scraping, simulador jogável, adversários de IA, assistência ao vivo, alterações em main, credenciais ou gastos.
