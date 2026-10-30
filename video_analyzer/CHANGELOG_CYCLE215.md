# Ciclo 215 — particionamento seguro de sessões longas (offline)

## Implementação

`offline_session_batch_planner.py` recebe um plano humano de 1–4 mesas com até 4.000 cortes declarados e anotações humanas vinculadas por SHA-256. Sem alterar os contratos dos módulos antigos (máximo de 100 cortes por execução), particiona cronologicamente os cortes em lotes compatíveis com o `offline_reviewed_math_runner`: até 100 cortes, 20 mãos elegíveis e 200.000 iterações por lote. Preserva IDs, mesas, timestamps, cartas declaradas, hipóteses de range e bloqueios. Recalcula as ligações SHA-256 de cada plano, anotações e fila; não executa Monte Carlo, OCR, FFmpeg ou avaliação estratégica.

Valida todas as mãos com o validador existente, recusa sobreposição na mesma mesa, mais de quatro mesas, timestamps superiores a 3.600 segundos, duplicações, anotações fora do plano, mutações de origem e sobrescrita. Publicação via diretório temporário e rename; `--verify` reconstrói todos os lotes, compara bytes, hashes, conteúdo exato dos diretórios e chama `runner.verify_inputs` em cada lote. Não incorpora vídeo original.

## Uso

```bash
cd video_analyzer
python offline_session_batch_planner.py PLAN.json ANNOTATIONS.json NEW_DIR
python offline_session_batch_planner.py --verify PLAN.json ANNOTATIONS.json NEW_DIR
python -m unittest -q test_offline_session_batch_planner
```

Para simular um lote explicitamente (não executado pelo particionador):

```bash
python offline_reviewed_math_runner.py NEW_DIR/batch-0001/plan.json NEW_DIR/batch-0001/annotations.json NEW_DIR/batch-0001/queue.json MATH_OUTPUT_NEW_DIR
```

## Testes locais

18 novos testes sintéticos: 300 cortes / 4 mesas / 3 lotes, 4.000 cortes / 40 lotes, rejeição de 4.001, limite de 20 mãos, orçamento de 200.000 iterações, hash/proveniência, symlinks, não sobrescrita, overlaps, resultados determinísticos e execução real de Monte Carlo em um lote sintético. Seleção de regressão (fila, motor, galeria, timeline, novo módulo): 98/98 aprovados localmente. Não equivale à suíte integral do repositório.

## Limitações

Não existe ainda um agregador entre lotes para gerar uma timeline única acima de 100 cortes; os consumidores atuais continuam limitados a 100 por lote. Falta vídeo autorizado e anotado de 3–5 minutos para medir OCR e reconstrução visual. Windows e sessões reais de 40–60 minutos não testados. Dados de teste são artificiais; nenhuma decisão real foi classificada. Sem mudanças em main, produção, credenciais, Actions ou custos.
