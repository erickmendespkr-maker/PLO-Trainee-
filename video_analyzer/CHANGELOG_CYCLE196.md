# Ciclo 196 — EV condicional offline (modelo terminal)

## Escopo
Novo offline_conditional_action_ev.py compara EV incremental **hipotético** de fold/call/raise em PLO5/PLO6, usando duas simulações Monte Carlo separadas: range para call e range condicionado a oponente pagar o raise. A probabilidade de fold é uma hipótese explícita, nunca inferida do OCR. O módulo não avalia uma ação real, não se conecta a plataformas de pôquer e não contém mesas jogáveis.

## Convenções de pote e equações
- pot_now já inclui a aposta do adversário, **antes** da decisão do herói; call_cost é quanto falta pagar.
- raise_extra é o adicional acima do call. Se pagar o raise, o adversário adiciona exatamente esse mesmo raise_extra (sem short call/side pot).
- EV incremental de fold = 0.
- EV de call = equity_call * (pot_now + call_cost) - call_cost.
- EV de raise = fold_probability * pot_now + (1-fold_probability) * [equity_raise_called * (pot_now + call_cost + 2*raise_extra) - (call_cost+raise_extra)].
- Intervalos propagados são **apenas** de amostragem Monte Carlo com ranges e fold probability fixos; os limites de diferença combinam marginais, **não** são IC conjunto calibrado.

## Uso
python video_analyzer/offline_conditional_action_ev.py reviewed_ev_input.json new_ev_report.json

Entrada obrigatória: call_scenario e raise_called_scenario com o mesmo herói/board/variante, formato aceito pelo offline_plo_equity_monte_carlo.analyze e manual_review_confirmed=true; pot_now, call_cost, raise_extra e fold_probability_assumed. Ambos os cenários podem ter ranges, sementes e iterações diferentes. Saída é JSON novo, nunca sobrescreve evidências.

## Testes verificados
- 11 testes novos sintéticos (incluindo PLO5/PLO6, royal flush de equity 100%, fórmulas, probabilidades extremas, determinismo, ranges separados, entradas inválidas e CLI).
- 45 testes selecionados aprovados (11 novos + 34 testes anteriores).
- Tentativa de suíte integral interrompida por limite de 120 s, sem resultado final; **não declarar a suíte integral aprovada**.

## Limitações / bloqueios
Sem rake, side pots, all-in, apostas futuras, múltiplos adversários, estimação de ranges/fold equity ou validação de ação observada. Não integra ainda o relatório visual com confirmação humana nem o gerador HTML. Não há vídeo autorizado/anotado de 3–5 minutos; precisão OCR e testes reais de 40–60 minutos permanecem bloqueados. Sem teste Windows.
