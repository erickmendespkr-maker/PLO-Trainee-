# PLO Trainee — Ciclo 248 (2026-10-31)

## Escopo preservado
Plataforma offline/assíncrona para analisar gravações de PLO5/PLO6 de até quatro mesas. Sem mesas jogáveis, bots adversários, conexão com plataformas de poker, auxílio em tempo real, mudanças em produção ou gastos.

## Implementação
- Novo módulo offline_street_split_index.py: relaciona o histórico de evidências por street do Ciclo 247 aos cortes MP4 com geometria temporal revisada do Ciclo 246.
- Revalida as observações originais contra o relatório por street e reexecuta o planejamento temporal a partir do vídeo, batch e revisão originais.
- Verifica SHA-256 do vídeo, MP4, relatórios e metadados, IDs de mesa/mão, timestamps da decisão, segmentos, coordenadas e indicadores de autorização.
- Gera street_split_index.html navegável localmente e street_split_index.json estruturado, sem scripts, com escape de HTML e rollback em falhas de publicação.
- Clipes sem correspondência de mão ou com decisão fora do intervalo declarado ficam explicitamente desvinculados. Decisões bloqueadas por transição continuam visíveis como bloqueadas.
- Evidências OCR continuam propostas não verificadas; a confiança não é calibrada e o módulo não autoriza equity/EV automático.

## Execução
Na pasta raiz do repositório, executar:
python video_analyzer/offline_street_split_index.py VIDEO.mp4 OBSERVATIONS.json STREET_DIR BATCH_DIR TEMPORAL_REVIEW.json SPLIT_DIR

Testes:
cd video_analyzer
python -m unittest -v test_offline_street_split_index.StreetSplitIndexTests

Os arquivos street_evidence_report.json e temporal_split_report.json, além dos MP4, precisam ter sido gerados pelos módulos anteriores a partir do mesmo vídeo.

## Testes e evidências
- 18 testes novos passaram localmente, incluindo dados sintéticos de quatro mesas, quatro MP4, uma decisão bloqueada, HTML escapado, vínculo por ID/timestamp, casos sem correspondência, adulteração, symlink, duplicidade e rollback.
- 69 testes selecionados passaram em diretório independente (18 novos + 20 do histórico por street + 31 testes executados pela classe de regressão temporal, incluindo testes herdados).
- A demonstração sintética reutiliza o vídeo e os quatro MP4 do Ciclo 246 e gera observações artificiais compatíveis com o mesmo vídeo. FFprobe confirmou a duração de um MP4.
- Código e testes publicados somente em feature/plo5-plo6-training.

## Limitações
- A associação depende de IDs de mesa/mão e timestamps declarados; não prova identidade real da mesa nem reconhece automaticamente cartas ou ações.
- Hashes e reconstrução de relatórios verificam consistência local, não autenticidade externa da gravação.
- Não houve validação com vídeo real autorizado/anotado, execução Windows, sessão de 40–60 minutos ou suíte integral.
- A etapa seguinte é uma revisão humana explícita de evidências por campo e a ligação controlada aos cálculos condicionais de equity/EV.
