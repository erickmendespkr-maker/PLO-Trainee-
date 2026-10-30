# Ciclo 218 — ZIP portátil de timeline e histórico matemático offline

Escopo: `docs/VIDEO_ANALYZER_SCOPE.md`; somente gravações enviadas pelo usuário,
PLO5/PLO6, até quatro mesas, sem assistência em tempo real, sem mesas jogáveis.

## Implementação

- Novo `offline_session_portable_bundle.py` com comandos `export`, `verify` e `open`.
- Exporta um ZIP independente contendo `plan.json`, `annotations.json`, os lotes
  preparados, histórico matemático, resultados JSON, timeline HTML e cortes MP4
  revisados quando presentes. **O vídeo original não entra no ZIP.**
- Inventário de arquivos e diretórios com SHA-256 e tamanho por arquivo. Escrita
  streaming, ZIP64, limites explícitos (12.000 membros, 1 GiB por arquivo,
  8 GiB de conteúdo total), sem sobrescrever destinos existentes.
- Rejeita membros duplicados, traversal, links simbólicos, conteúdo adulterado,
  diretórios/arquivos extras e alegações indevidas de OCR ou avaliação de ações.
- Verificação profunda em extração temporária: reexecuta validadores existentes
  de plano, lotes, fila, histórico, MP4 e HTML. **Não** recalcula Monte Carlo.
- Abertura em novo diretório com validação antes da publicação do resultado.

## Como usar

A pasta `SESSION_ROOT` deve conter a estrutura já gerada pelos módulos
`offline_session_batch_planner`, `offline_session_batch_history` e
`offline_session_batch_timeline`:

```text
SESSION_ROOT/
  plan.json
  annotations.json
  batches/
  workspace/
    results/
    batch_timeline.html
    clips/               # opcional, somente cortes MP4 revisados
```

```bash
python video_analyzer/offline_session_portable_bundle.py export SESSION_ROOT sessao.zip
python video_analyzer/offline_session_portable_bundle.py verify sessao.zip
python video_analyzer/offline_session_portable_bundle.py open sessao.zip SESSAO_ABERTA
```

Abra `SESSAO_ABERTA/workspace/batch_timeline.html` no navegador, conforme as
restrições de reprodução de `file://` do ambiente. Não substitui o vídeo original.

## Testes locais executados

- 16 novos testes sintéticos, incluindo 305 mãos em quatro mesas e quatro lotes,
  MP4 gerado por FFmpeg, corrupção de HTML/histórico/vídeo, tentativa de traversal,
  links simbólicos, duplicatas, retomada de histórico parcial e bloqueio de sobrescrita.
- Suíte selecionada de 159 testes (novos + regressão dos módulos empacotados): OK.
- Repetição da suíte após extrair o pacote de código: registrar resultado no ciclo.
- Demonstração sintética: 305 mãos, 4 lotes, 1 MP4 de 4 segundos; exportação,
  verificação e abertura do ZIP testadas. Não é vídeo de pôquer real.

## Não verificado / bloqueios

- Sem vídeo real autorizado e anotado de 3–5 minutos: OCR, identificação de mãos,
  cartas e ações, calibração de confiança e análise estratégica real pendentes.
- Não validado em Windows ou com gravações reais de 40–60 minutos.
- SHA-256 e validação estrutural não provam autenticidade da gravação, correção
  das cartas declaradas ou adequação de ranges hipotéticos.
- A verificação profunda usa os validadores locais do repositório, não auditoria
  matemática independente de cada iteração Monte Carlo.

Sem GitHub Actions, alterações na main, produção, credenciais ou gastos.
