# Bloco 12 — ingestão auditada PLO5 (25/11/2026)

## Caminho executável

`python video_analyzer/plo5_ingest_job.py recording.mp4 regions.json private_uploads jobs.db evidence_jobs --interval 30 --pixel-checks 32`

O CLI reutiliza local_ingest, OfflineJobStore, offline_ingest_audited_pipeline e seus auditores independentes; não cria outro reconhecedor. A configuração JSON exige 1–4 regiões retangulares não sobrepostas e alinhadas, por exemplo {"tables":[{"table_id":1,"x":0,"y":0,"width":320,"height":180}]}. Adaptar às dimensões da gravação. Não representa detecção automática de mesas.

Cada job tem ID e SHA-256 da cópia registrada. A cópia é verificada contra os bytes originais antes do enqueue; claim_job altera atomicamente apenas o job solicitado. A configuração é copiada para o pacote privado e os resultados são publicados juntos após as auditorias. A fila termina em review_required, nunca em completed somente por extrair quadros. O result_path aponta para job_binding.json, que vincula ID, tentativa, variante 5, SHA da gravação e cinco arquivos de evidência/configuração. read_bound_evidence revalida esses hashes e os recortes antes da próxima etapa.

Limites: MP4 na nova entrada PLO5, até 4 GiB pela fila existente, 0,5–3660 s pelo preflight auditado e geometria até 3840x2160. A tolerância adicional de 60 s atende gravações com cauda de contêiner, incluindo os 3610,1 s conhecidos. O limite de duração é política, não benchmark. A seleção de pixels usa subconjunto equilibrado por região para respeitar a auditoria independente; orçamento não divisível pode usar menos verificações. O seletor legado mantém o comportamento padrão. A auditoria PTS/hash cobre todos os recortes amostrados, não todos os frames ou decisões do vídeo.

## Validação local

Python 3.13.5, FFmpeg 7.1.5, SQLite e Pillow 12.3.0. Suíte local selecionada: 125 testes aprovados, 10 novos, 84 regressões estratégicas e 31 regressões de ingestão/auditoria existentes; 17,939 s. Dependências de vídeo recuperadas do repositório pelo conector e conferidas por hashes. Sem alegação de execução da suíte integral do repositório.

MP4 sintético de 2 s, 128x128, 5 fps, quatro regiões: 12 recortes auditados por PTS/SHA, quatro comparações independentes de pixels usando uma passagem de redecodificação, estado review_required. Também executados fixtures preexistentes VFR, PTS com offset, uma região, 65 s e testes de adulteração da cópia, fonte, recortes e relatórios, isolamento de jobs e falhas de auditoria. Teste de limite 3610,1/3660/3660,1 s usa metadados simulados, não uma gravação de uma hora.

## Pendências e limites

- Sem vídeo real autorizado disponível localmente neste ciclo. Detecção automática de mesas, limites de mãos, OCR, cartas e decisões permanecem pendentes; próximos blocos 13–19.
- Amostragem esparsa não é cobertura de mãos. Nenhum EV, GTO ou resultado financeiro é autorizado pelo pacote.
- Interface web, desempenho em 60 min, Windows e recuperação automática de job interrompido ainda não validados. Se houver falha de banco após publicação do pacote, a pasta pode ficar órfã; não apagar automaticamente, reconciliar com a fila antes de reprocessar.
- Bloco 11B preservado: autorização de dados GTO e compilação/execução do Poker-Eval pendentes. Não altera a database PLO5 de equity.
- Sem alteração de main, deploy, automação, serviços externos ou publicação de vídeo privado.
