# Ciclo 124 — Limites pot-limit condicionados a um ledger explícito

Escopo: somente vídeos gravados PLO5/PLO6; **sem** simulador, jogo ao vivo, conexão com salas, ação automática ou veredictos de erro estratégico.

## Entrega

`offline_pot_limit_decision_bounds.py` calcula os limites condicionais de uma decisão usando valores declarados em **unidades inteiras de fichas**. Não converte o campo `amount` dos históricos anteriores: ele não distingue aumento incremental de aposta total. O novo contrato usa explicitamente `target_contribution_street` (total comprometido pelo jogador nesta street após a ação).

Exemplo sintético: pote imediatamente antes da decisão = 100; contribuição do jogador nesta street = 10; maior contribuição = 30; stack restante = 200; incremento mínimo de raise completo = 20. Então `to_call=20`, pote após call hipotético = 120, teto pot-limit do total comprometido = `min(10+200, 10+20+120)=150`, mínimo de raise completo = 50. Um raise-to de 100 é **aritmeticamente compatível com esses valores declarados**, não verificado no vídeo.

O ledger exige `schema_version=1`, `variant=PLO5|PLO6`, `source=synthetic|human_transcribed`, `pot_before_action`, `actor_contribution_street`, `highest_contribution_street`, `actor_stack_remaining`, `min_full_raise_increment` (inteiro ou null), `observed_action={kind,target_contribution_street}`, `notes`. `pot_before_action` inclui todas as fichas já comprometidas, inclusive apostas desta street. O teto considera o call antes de calcular o aumento máximo do pote; o stack restante limita o teto. Uma aposta all-in curta é sinalizada separadamente porque pode não reabrir a ação.

Uso offline:

```bash
python video_analyzer/offline_pot_limit_decision_bounds.py ledger.json novo_relatorio.json
python -m unittest video_analyzer/test_offline_pot_limit_decision_bounds.py
```

Saídas preservam `betting_rules_verified=false`, `video_evidence_verified=false`, `ready_for_equity_or_ev=false`, `automatic_clip_selection_authorized=false`. O relatório **não** declara uma aposta ilegal: apenas flags condicionais a entradas humanas/sintéticas. Não há reconstrução da ordem de ações, side pots, elegibilidade multiway, OCR, ranges ou EV.

## Testes locais

25 testes novos de aritmética, all-in curto, call, check, validação estrita, JSON duplicado, symlink e não sobrescrita. Regressão selecionada: 29 testes anteriores de triagem + 25 novos = **54 aprovados** localmente. Suíte completa e CI remoto não executados.

## Bloqueios

Falta gravação autorizada anotada de 3–5 minutos para medir precisão do OCR, identificar mãos e validar valores reais. O problema de duração de clipes no último quadro da gravação continua pendente. Próximo ciclo: derivar um ledger auditável de ações reconstruídas (sem presumir completude) e associar evidência visual por campo.
