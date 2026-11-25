# Bloco 37 — comparação com anotação humana PLO5 (25/11/2026)

## Entrega

video_analyzer/plo5_ground_truth.py gera um template de anotação a partir do manifesto auditado do bloco 12, sem copiar previsões para os campos de referência. CLI:

    python video_analyzer/plo5_ground_truth.py jobs.db JOB_ID annotations.json

Preencher reviewer, independent_review=true e truth em cada quadro efetivamente revisado; dataset_kind distingue real_recording e synthetic_fixture por declaração. Campos opcionais: visible, hero_seat (1–6), hero_cards (cinco privadas, ordem indiferente), board (0/3/4/5 cartas, ordem visual), position, pot_bb, hero_stack_bb (strings decimais em BB), hero_action_label (fold/check/call/bet/raise/all_in), hand_id (identificador humano da mão no quadro), decision_action (classe de ação realmente observada no quadro). Omitir desconhecidos; null para ausência explicitamente anotada de cartas privadas/rótulo; board vazio é lista vazia. Não inferir ação executada de rótulo persistente. Revisor e independência não autenticados.

    python video_analyzer/plo5_ground_truth.py jobs.db JOB_ID validation.json --drafts drafts.json --annotations reviewed.json --bundle decision_bundle.json

Bundle opcional do bloco 32. Valida identidade job/fonte/manifesto, cobertura e vínculo de quadros, PTS, hashes dos recortes, duplicatas, formato de cartas e integridade dos arquivos ao fim. Calcula por campo e mesa cobertura, acurácia sobre todos os anotados e sobre previsões emitidas, contagens TP/TN/FP/FN, precisão e recall de correspondência exata. Uma previsão positiva errada para uma referência positiva conta FP e FN; ausência confirmada não é abstenção; leitura desconhecida nunca conta como acerto. Para cartas privadas desconhecidas, ausência não é inferida. Hero seat avaliado somente como candidato de assento declarado com cinco cartas pré-flop, não detector independente. Campos financeiros têm erro absoluto médio/máximo somente onde houve previsão. Mudança de hand_id entre quadros amostrados adjacentes na mesma mesa é comparada à mudança de segmento; não é medida de precisão temporal nem completude das mãos. Quadros não atribuídos geram abstenção de fronteira. Cobertura de decisão compara classe de ação anotada e relatório de origem com hipóteses comparáveis; não valida sizing ou EV real. Resultados não promovem flags de vídeo, GTO ou seleção automática.

## Testes

7 novos testes aprovados (1,555 s), mais 328 regressões selecionadas do bloco 36, executadas em três invocações: contratos 8, desempenho 5, integração 47, estratégia 78, matemática 93, ingestão 47, reconhecimento 42 e exportação 8. Total 335 testes aprovados, sem erros ou skips nas execuções finais. Inventário de 81 arquivos anteriores conferido pelo runner. Primeira execução nova falhou no fixture que esperava rejeitar um nome de revisor válido; corrigido para nome vazio. Testes cobrem erro/abstenção, fronteiras, identidade, duplicatas, entradas inválidas, rótulo all_in/blank e template/CLI com MP4 sintético de duas mesas e cobertura de dois relatórios condicionais. Fixture de quatro quadros: 3/4 potes exatos, MAE 0,5 BB, erro máximo 2 BB; dois rótulos anotados, um incorreto e um sem previsão. Estes números não representam desempenho em poker real.

## Bloqueio de dados reais

Busca nos arquivos disponíveis da conversa/Library não recuperou as gravações anteriores; vídeos locais existentes são fixtures sintéticos. O Drive confirmou o MP4 Gravar_2026_11_17_20_04_04_346.mp4 (791630253 bytes); a tentativa autenticada de obtenção dos bytes foi recusada com HTTP 413, acima do limite de 268435456 bytes. Não foram inspecionados quadros desse vídeo nesta etapa. Nenhuma precisão em gravação real medida. Para validação real, fornecer amostras MP4 acessíveis menores que o limite, preferencialmente trechos representativos com mãos completas e anotação independente. Não publicar vídeo privado ou anotações pessoais no repositório.

## Estado

Bloco 37 parcial: infraestrutura de avaliação implementada/testada, validação real ainda pendente. Preservar 11B, 13–19, 24, 27, 28, 32–35. Próximo bloco 38: teste integral de sessão real de uma hora/quatro mesas, cobertura e desempenho. Sem alterações em main, deploy ou automação.
