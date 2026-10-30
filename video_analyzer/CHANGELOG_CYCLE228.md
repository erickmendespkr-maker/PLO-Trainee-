# Ciclo 228 — importação de revisões por mão/street (offline)

## Escopo
Implementado `offline_hand_street_review_import.py` para importar o JSON exportado pelo editor do ciclo 227. Não acessa redes, mesas de poker ou serviços externos. Não executa equity/EV e não libera mãos para matemática.

## Uso
```bash
python video_analyzer/offline_hand_street_review_import.py \
  reconstruction.json worksheet.json hand_street_review_draft.json new_review_ledger.json
```

- Recria o worksheet a partir da reconstrução original e compara o conteúdo integral. Isso impede substituir candidatos OCR ou proveniência na cópia de worksheet.
- Exige que o draft preserve todos os campos imutáveis, mãos, mesas, streets, slots, hashes e candidatos OCR; permite alterar apenas `review_status` e `reviewer_value`.
- Aceita `unreviewed`, `rejected`, `unknown` sem valor; `confirmed_by_reviewer` exige declaração válida. Cartas devem usar `As`, `Kd` etc.; variante PLO5/PLO6; pote e stack em formato decimal simples (sem unidade assumida).
- Sinaliza cartas repetidas, lacunas no board, cartas privadas incompletas, variante incompatível, ausência de ação/pote/stack, divergência do OCR e street não comprovada.
- Registra SHA-256 de reconstrução, worksheet e draft, preservando hash declarado do vídeo e hash do ledger anterior. Hash garante integridade dos bytes fornecidos, **não** autenticidade das declarações humanas.
- Rejeita chaves JSON duplicadas, NaN, symlinks, alterações de estrutura, sobrescrita de saída e dados fora do formato.

## Testes executados no ambiente local
- 50 testes novos do importador e 95 testes selecionados de regressão dos módulos adjacentes: **145/145 aprovados**.
- Importação de um draft sintético existente com quatro mesas: 4 mãos, 60 campos, 1 declaração manual não autenticada, 0 mãos liberadas para equity.
- Testes independentes com extração do pacote ZIP devem ser registrados separadamente; os testes aqui não representam a suíte integral do repositório.

## Limitações e bloqueios
- O resultado é um ledger de revisão **não verificado**; `eligible_for_equity=0` e `equity_or_ev_calculated=false` sempre.
- O editor do ciclo 227 não associa ações/pote/stack a uma street temporalmente comprovada. Isso continua sinalizado, não é inferido.
- Falta gravação autorizada e anotada de 3–5 minutos para aferir precisão de OCR/visão; testes com sessões reais de 40–60 minutos e Windows permanecem pendentes.
- Próximo: revisão de evidência de vídeo por mão e street, com confirmação independente e um contrato separado para parâmetros Monte Carlo (sem promover automaticamente este ledger).
