# Ciclo 225 — importador de rascunhos OCR (fail-closed)

## Entrega
- Novo `video_analyzer/offline_ocr_review_draft_import.py` para ler o rascunho JSON exportado pela interface do ciclo 224.
- Revalida o worksheet, o manifesto de quadros e os PNGs, hashes SHA-256, mesa, mão, slot, campo, ordem das observações, timestamps e vínculo com o quadro.
- Aceitação só é registrada se o quadro da mesma mão/mesa estiver a no máximo 0,25 s do timestamp. Correção textual não pode ser aceita como OCR original.
- Detecta candidatos selecionados conflitantes no mesmo slot e carta repetida entre slots.
- Exporta ledger JSON novo, preservando seleção humana, correções e evidências de quadro como **alegações não autenticadas**.
- `eligible_for_equity=0`, `math_ready=false` e `equity_or_ev_calculated=false` são invariantes. Não produz arquivo de anotações `human_confirmed`, nem alimenta automaticamente Monte Carlo.

## Uso
```bash
python video_analyzer/offline_ocr_review_draft_import.py \
  DIRETORIO_DE_QUADROS WORKSHEET.json RASCUNHO_EXPORTADO.json NOVO_LEDGER.json
```

## Testes locais
- 22 testes novos sintéticos no importador, mais 21 testes do módulo de revisão do ciclo 224: **43/43 aprovados** no ambiente local.
- Cobertura inclui hashes adulterados, tabela errada, reordenação/omissão de decisões, tentativa de habilitar equity, correções, aceitação sem quadro temporal, symlink e PNG alterado.
- GitHub Actions não executado; suíte integral do repositório não executada.
- Os hashes Git dos dois arquivos Python publicados foram conferidos com as versões locais testadas.

## Limitações
- O draft HTML pode ser editado ou forjado pelo usuário: hash e consistência não autenticam quem revisou ou a veracidade das cartas.
- Sem vídeo real autorizado e anotado de 3–5 minutos, precisão de OCR e reconstrução de mãos permanecem desconhecidas.
- Não testado no Windows nem com sessões de 40–60 minutos.
- Para chegar a uma fila matemática segura, é necessária uma etapa distinta de revisão explícita das cartas completas, variantes e ranges, com tratamento de incerteza.

## Próximo passo
Criar reconstrutor de mãos por slots e evidências revisadas, sinalizando campos faltantes, conflitos e ambiguidades. Nunca inferir cartas ocultas como fatos.
