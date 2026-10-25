# PLO Trainee — Ciclo 105: dossiês estruturados por intervalo nominal

Escopo consultado: `docs/VIDEO_ANALYZER_SCOPE.md`. Somente vídeos gravados PLO5/PLO6, processamento offline e revisão humana. Nenhum simulador de mesas, IA adversária ou integração com pôquer ao vivo.

## Entrega

- `offline_job_hand_evidence_dossier.py` transforma **intervalos marcados manualmente** (Ciclo 104) e a timeline OCR revalidada (Ciclo 102) em dossiês de evidências por mesa/intervalo. O ponto de entrada `dossiers_job()` executa novamente `timeline_job()` para auditar a gravação, imagens e decisões humanas antes de montar o resultado.
- Cada dossiê preserva referências de imagem, hash SHA-256, timestamp **nominal**, texto OCR original não verificado, anotação humana não interpretada, status e confiança **subjetiva**. Mantém campos separados para `hero_cards`, `board`, `pot`, `bet`.
- Destaca ausência de campos, OCR pendente/incerto/rejeitado, divergência entre valores de um mesmo campo no **mesmo** timestamp e mudanças de valores **entre** timestamps. Mudanças ao longo do tempo não são rotuladas como contradições: podem refletir a progressão natural da mão.
- Um worksheet manual de reconstrução de mão é criado **inteiramente vazio**. OCR confirmado não vira automaticamente carta, valor, ação, range ou hipótese matemática.
- Vincula dossiês a digests canônicos SHA-256 da timeline e dos intervalos revalidados; rejeita submissões desatualizadas, sobreposições, alterações de evidências e tentativas de elevar o status para análise matemática.
- Exportação JSON local exclusiva (`O_EXCL`, `O_NOFOLLOW` quando disponível), sem sobrescrita; limite de 16 MiB. Até 4 mesas, 2.000 intervalos e 20.000 observações. Não modifica a fila nem a gravação.
- `hand_reconstruction_verified=false`, `ready_for_equity_or_ev=false` e `automatic_clip_selection_authorized=false` em todos os dossiês e na saída geral. **Nenhum cálculo de equity/EV nem clipe é gerado aqui.**

## Uso

```bash
# Criar uma submissão de intervalos pelo módulo do Ciclo 104 e preenchê-la manualmente.
python video_analyzer/offline_job_hand_interval_review.py jobs.sqlite <job_id> results/ > intervals.json

# Reauditar as evidências e gerar dossiês sem alterar arquivos:
python video_analyzer/offline_job_hand_evidence_dossier.py jobs.sqlite <job_id> results/ --submission intervals.json

# Exportar JSON uma única vez (não sobrescreve):
python video_analyzer/offline_job_hand_evidence_dossier.py jobs.sqlite <job_id> results/ --submission intervals.json --export
```

`intervals.json` deve incluir `reviewer` e os `intervals` preenchidos pelo revisor. Os valores numéricos e strings de OCR não são interpretados como fatos matemáticos.

## Testes executados localmente

- `python -m unittest -q test_offline_job_hand_evidence_dossier`: **24 testes aprovados**.
- Seleção de regressão (módulos offline, revisão, matemática e exportação de clipes): **278 testes aprovados**, incluindo os 24 novos.
- Demonstração sintética: 4 mesas, 4 intervalos, 12 observações e **zero** dossiês autorizados para matemática.
- Benchmark sintético JSON: 4.800 observações, 120 intervalos e duração nominal de 60 minutos; **não** representa OCR/FFmpeg em vídeo real.
- Testes com componentes do snapshot local do Ciclo 98 complementados pelos ciclos 99–104; ainda **não** equivalem à suíte integral da árvore exata da branch GitHub.

## Bloqueios e limites

- Sem gravação autorizada de 3–5 minutos com anotações humanas para aferir reconhecimento de cartas, ações e limites de mãos.
- Timestamps são amostras nominais, não PTS do vídeo confirmados.
- Sem reconstrução confiável da sequência de ações, stacks e ranges. O motor Monte Carlo existente só pode receber cenários matemáticos validados independentemente.
- Regressão integral da árvore exata do GitHub e fluxo end-to-end com vídeo real continuam não verificados.
