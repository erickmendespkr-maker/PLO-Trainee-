# Ciclo 198 — HTML offline para sensibilidade de EV vinculada a cartas confirmadas

## Escopo
Somente a branch `feature/plo5-plo6-training`. Implementado `offline_acknowledged_ev_sensitivity_html.py` e `test_offline_acknowledged_ev_sensitivity_html.py`. Não foram alterados main, produção, credenciais, ações GitHub ou custos.

## Uso

```bash
python video_analyzer/offline_acknowledged_ev_sensitivity_html.py \
  ACKNOWLEDGED_REPORT.json SENSITIVITY.json clip.mp4 NEW_EXPLANATION.html
```

Os três arquivos de entrada devem ser locais; o MP4 deve se chamar `clip.mp4` e ficar ao lado do HTML novo. A página não usa recursos remotos ou JavaScript e inclui vídeo, equity de cartas declaradas e confirmadas por humano, gráfico SVG de EV raise por probabilidade hipotética de fold, tabelas fold/call/raise e avisos sobre limites do modelo.

## Controles
- Reutiliza a validação do relatório de equity com confirmação humana e SHA-256 do MP4.
- Exige coincidência de variante, cartas privadas e board entre relatório confirmado e sensibilidade EV.
- Rejeita grades de ação, afirmações falsas de OCR/identidade verificada, flags de ranges não hipotéticos, probabilidades fora de ordem, alterações de EV inconsistentes com equity/pote/custo, limites marginais inválidos e labels inseguras.
- Saída HTML somente nova, na pasta do clipe; confere hashes dos arquivos antes e depois de renderizar.
- Os ranges usados nos cenários EV **não são comprovadamente iguais** ao range usado no relatório de equity original. A coincidência das cartas não transforma ranges em observações. Não se refaz a auditoria do vídeo original nem dos PNGs.

## Testes locais em 29/10/2026
- **21 testes novos aprovados** (`test_offline_acknowledged_ev_sensitivity_html`).
- **66 testes selecionados aprovados** incluindo testes do renderizador anterior, confirmação humana e sensibilidade.
- CLI executada com um MP4 sintético real de **2,0 segundos** gerado por FFmpeg; FFprobe confirmou duração. HTML e hash do MP4 foram produzidos.
- Tentativa da suíte local integral `test_offline_*.py` excedeu 180 segundos; **não** declarar a suíte integral aprovada.
- Chromium headless para screenshot do HTML excedeu 18 segundos; renderização visual em navegador **não verificada**.
- Testes de cards/EV usam anotações sintéticas, sem comprovar OCR, PTS real ou precisão estratégica.

## Bloqueio e próximo ciclo
Ainda falta vídeo autorizado e anotado de 3–5 minutos para medir precisão de cartas, ações e segmentação. Próximo: integrar a geração de sensibilidade diretamente à revisão manual, rastrear parâmetros de ranges com hashes e preparar benchmark de vídeo multi-mesa sem dados reais quando necessário.
