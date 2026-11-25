# PLO Trainee — plano de execução revisado (PLO5 exclusivo)

Revisão de 25/11/2026. Substitui as metas futuras de PLO4/PLO6 no plano de 39 blocos, sem apagar o histórico dos blocos 01–10. Manter a branch feature/plo5-plo6-training (nome histórico) e os componentes existentes que não atrapalhem PLO5. Nenhum trabalho novo em outras variantes.

## Produto e objetivo de aceitação

Análise offline/assíncrona de sessões gravadas de cash game PLO5, até quatro mesas, com cortes MP4 completos e explicações técnicas em português. Avaliar todas as decisões visíveis, inclusive folds e mãos ganhas; não apenas perdas financeiras. Hero é identificado pelas cartas privadas visíveis pré-flop quando a evidência do layout sustenta essa identificação. Sem assistência ao vivo, RTA, mesas jogáveis, Gemini ou serviços pagos.

O PLO Spot é referência do nível de detalhamento desejado (frequências por ação, EV, contexto pré-flop), não autorização para copiar sua base, código ou interface. Não extrair sistematicamente soluções sem permissão. Usar somente dados com licença compatível e comprovada, ou cálculos próprios. PLO Mastermind permanece referência conceitual pública, sem ingestão de conteúdo do serviço. Não chamar equity bruta, heurísticas ou simulações condicionais de GTO.

## Contrato de análise por decisão

- Evidência: mão/mesa, PTS, cartas visíveis, board, posição, street, sequência de ações, sizing, stacks efetivos, pote, rake/ante e quantidade de jogadores. Desconhecido permanece desconhecido.
- Referência: modalidade PLO5, modelo/versão, fonte, licença, contexto exato e unidade/base de EV; frequências e EV por ação/sizing apenas quando fornecidos por referência compatível. Não fabricar valores, converter equity em frequência nem extrapolar heads-up para 6-max.
- Comparação: ação realizada, alternativas, melhor EV disponível e diferença max(EV das alternativas)-EV da ação real, somente com base comum e conjunto de alternativas declarado. Frequência baixa não prova erro; considerar incerteza, sensibilidade e ações mistas. Indicar cobertura parcial.
- Rotular resultados separadamente: referência de solver autorizada, solução própria aproximada com qualidade verificada, EV modelado condicional, heurística descritiva, NO_MATCH ou INSUFFICIENT_DATA. Nunca apresentar hipótese como solução GTO.
- Pré-flop: RFI, folds, calls, 3-bet/4-bet, defesa de blinds, pares, naipes, conectividade, blockers, posição, stack e rake.
- Pós-flop: textura, nuts/redraws, equity contra ranges explícitos, pot odds, SPR, fold equity, implied/reverse implied odds sob hipóteses, range/nut advantage quando demonstrável.
- Relatório: resultados financeiros reconciliados separados do EV loss e da variância; leaks por contexto com denominadores, cobertura, incerteza e número de decisões avaliáveis. Não somar estimativas incompatíveis nem atribuir desvio à sorte sem base.
- Cada conclusão rastreável a evidência, referência ou cálculo. Clipes MP4 da mão completa com análise associada, não afirmações não sustentadas.

## Blocos restantes (mesma numeração; subdividir se a capacidade do disparo exigir)

| Bloco | Trabalho e critério verificável |
|---|---|
| 11 | Prioridade: importar CSV PLO5 SolvePoker recebido em tabela de equity separada; conferir licença/atribuição/hash e contagens, preservar descrições ambíguas de naipes sem inventar classe exata. Investigar via fontes oficiais permissão de PLO Spot e SolvePoker Notebook; avaliar licença e exemplos PLO5 de Poker-Eval (jejellyroll-fr). Testar se possível; não declarar solver 6-max funcional sem evidência. Se necessário, dividir 11A aquisição, 11B avaliação solver. |
| 12 | Consolidar ingestão de vídeo MP4 e extração de quadros/PTS; ligar evidências ao job. |
| 13 | Detectar mesas e limites de mãos; medir falsos positivos com fixtures. |
| 14 | Reconhecer exatamente cinco cartas privadas e board; duplicatas e confiança. |
| 15 | Reconhecer posição, blinds, stack efetivo, pot e sizing; preservar unidade e evidência. |
| 16 | Reconhecer ações, folds e ordem; registrar cada decisão e evidência temporal. |
| 17 | Reconstruir hero e histórico por street; incluir decisões fold e desenrolar da mão. |
| 18 | Reconstruir showdown, vencedores, retornos, premiações e rebuys. |
| 19 | Reconciliar ganhos/perdas BB com ledger; separar resultado financeiro de estratégia. |
| 20 | Validar avaliador PLO5 (2 privadas + 3 comunitárias); benchmarks independentes. |
| 21 | Ranges ponderados, Monte Carlo, equity exata quando viável, erro e sensibilidade. |
| 22 | EV incremental de fold/call/bet/raise com sizing, rake e hipóteses explícitas. |
| 23 | Comparação de EV por ação, EV loss, cobertura e incerteza; não confundir variância. |
| 24 | Integrar database, decisões reconstruídas e motor de cálculo; lookup exato, sem mistura de contextos. |
| 25 | Classificar mãos PLO5 e identidade de naipes; separar equity agregada da classe exata. |
| 26 | Pares, conectividade, suits, blockers e potencial de nuts; explicar sem inventar frequências. |
| 27 | RFI, calls, defesa de blinds e 3-bet por posição e stack; frequências/EV apenas se sustentados. |
| 28 | 4-bet, stack-off, sizing e comparação pré-flop; solução própria limitada rotulada e testada. |
| 29 | Texturas flop/turn/river, nuts e range/nut advantage com ranges declarados. |
| 30 | Draws, redraws, backdoors, blockers, SPR e pot odds. |
| 31 | Implied/reverse implied odds e multiway sob modelos explícitos; sensibilidade. |
| 32 | Leaks recorrentes por posição, street, ação e stack com denominadores e cobertura. |
| 33 | Relatório técnico individual em português: frequências, EV, ação real, alternativas, explicação e nível de confiança; separar erros, perdas e variância. |
| 34 | Relatório consolidado de sessão e exportação MP4 da mão completa; vincular análise ao corte. |
| 35 | Otimizar CPU/RAM/disco e cache; medir impacto, sem sacrificar precisão. |
| 36 | Testes unitários e integração offline, incluindo mãos sem match, ações mistas e dados insuficientes. |
| 37 | Validar mãos reais anotadas contra referência humana; medir precisão de campos e decisões avaliáveis. |
| 38 | Validar sessão completa até quatro mesas/uma hora; relatório e clipes auditáveis. |
| 39 | Corrigir falhas, instalação/Windows, manual, publicação do MVP somente com critérios comprovados. |

## Regras de execução

Cada disparo: conferir HEAD, implementar alterações reais, executar testes possíveis, publicar e verificar a branch. Se houver bloqueio, avançar em tarefas independentes, mantendo o item bloqueado pendente. Não declarar testes ou dados reais sem evidência. Não modificar main, deploy ou outros repositórios. Não duplicar a automação. Não publicar vídeo privado ou dados proprietários. A numeração histórica é mantida; não representa garantia de prazo ou percentual do produto. A aquisição da base GTO e a validação de um solver próprio são dependências abertas, não entregas já realizadas.
