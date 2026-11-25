# Bloco 18 — candidatos de resultados PLO5 (25/11/2026)

## Entrega

video_analyzer/plo5_result_candidates.py reutiliza OCR e validação de valores do bloco 15, ROIs do bloco 14, pacote auditado do bloco 12 e rascunho JSON do bloco 17. Exige job, variante 5, SHA do vídeo e manifesto, status não verificado, cobertura exata de todos os recortes, PTS e SHA correspondente, mesas e assentos compatíveis. Registra SHA do rascunho e perfil e revalida os arquivos ao final. Um rascunho externo estruturalmente compatível não é uma autenticação de sua atribuição de mão; continua sendo revisão.

CLI: python video_analyzer/plo5_result_candidates.py jobs.db JOB_ID drafts.json profile.json new_report.json --threshold 0.75 --max-tasks 1024 --max-gap 10

Perfil: variant=5, tables com table_id e seats (2–6 assentos declarados); cada assento tem seat e result [x,y,w,h] em pixels do recorte. Uma ROI por assento, sem sobreposição. O perfil deve corresponder aos assentos declarados no rascunho. Rótulos exatos em português/inglês para showdown, premiação, devolução e rebuy/top-up, incluindo indicação de pote principal ou lateral numerado 1–5 quando explícita. Valores positivos com unidade BB/chips/fichas, sem suposições de unidade; rótulos sem valor preservam null. Não reconhece automaticamente animações de fichas ou cartas dos adversários.

Agrupa rótulos idênticos e valores idênticos em episódios por mesa, assento e segmento; lacunas, duplicatas, observações incertas e quadros não atribuídos interrompem o agrupamento. Não soma episódios, não infere payout por variação de saldo, não trata rebuy como lucro, não confunde devolução com premiação. Um pote sem identificação explícita fica sem pot_id. Não calcula potes laterais a partir de contribuições nem comprova vencedores pela combinação de cartas. Mantém todas as observações, inclusive sem atribuição. Resultado financeiro null, payouts_verified e winners_verified false, nenhuma autorização de EV ou clipe automático.

## Testes reais do ambiente Linux

167 testes distintos selecionados aprovados: 82 regressões de vídeo/equity concluíram com ok no log da execução conjunta; a execução conjunta atingiu timeout antes de terminar o último teste novo e os estratégicos. Os sete novos foram executados separadamente, todos aprovados (3,104 s); as 78 regressões estratégicas foram executadas separadamente, todas aprovadas (0,499 s). Não afirmar uma execução única completa ou a suíte integral. A suíte local preserva os classificadores parciais do bloco 13. Os módulos plo5_hand_drafts, plo5_context_candidates e plo5_ingest_job conferidos localmente contra os blobs do HEAD anterior.

MP4 sintético H.264, 480x320, 2 s, 5 fps, três recortes, cinco assentos: 15/15 rótulos OCR recuperados e cinco episódios (WIN MAIN 60 BB, WIN SIDE 1 20 BB, RETURN 5 BB, REBUY 100 BB, SHOWDOWN). O rascunho do teste foi construído sinteticamente a partir do manifesto real do fixture; não representa reconstrução de uma mão verdadeira nem execução dos quatro reconhecedores nesse teste. Testes incluem unidades ambíguas, isolamento de mesa/assento/segmento, persistência, lacunas, duplicatas, ausência de atribuição, perfil inválido, origem incompatível, orçamento e adulteração de recortes.

## Estado

Bloco 18 parcial: candidatos de rótulos vinculados a evidência; faltam calibração de uma sala real, reconhecimento de showdown sem texto, verificação das cartas e vencedores, construção e reconciliação dos potes principal/laterais, empates, rake, devoluções, rebuys e sequência de pagamentos. Os limites da amostragem esparsa e dos perfis anteriores continuam. Nenhuma mão real analisada. Preservar blocos 11B, 13–17. Próximo bloco 19: reconciliação financeira condicional com contribuições, devoluções, premiações, ajustes externos e saldos; manter desconhecidos em aberto e separar resultado financeiro de EV. Sem alterações em main, deploy, automação ou dados privados.
