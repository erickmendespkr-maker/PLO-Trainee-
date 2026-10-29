# Ciclo 185 — fila de triagem vinculada a evidências OCR e vídeo local

## Entrega

`offline_triage_review_dashboard.py` une a linha do tempo (`offline_action_bet_timeline.py`), a fila heurística (`offline_action_review_triage.py`) e o relatório de evidências (`offline_action_evidence_viewer.py` ou `offline_verified_evidence_bundle.py`) em uma página HTML offline de leitura. A página exibe as ações OCR selecionadas, mesa, variante, mão, timestamp, prioridade heurística, recortes ROI, valores OCR de pote/aposta próximos e alertas. O usuário pode selecionar **localmente** um MP4/WebM e navegar para a janela sugerida, sem upload nem acesso à rede. A página não identifica a mesa automaticamente no vídeo e não recorta clipes.

## Segurança e limites

- Recalcula a fila a partir do histórico e rejeita prioridades ou candidatos adulterados.
- Exige SHA-256 idêntico da linha do tempo na fila e no relatório de evidências; confere correspondência de mãos, eventos, timestamps e valores OCR.
- Verifica hashes das imagens ROI, impede symlinks de arquivos de entrada, nomes de caminhos arbitrários, sobrescrita e saída dentro da pasta de evidências; publica em diretório novo somente após validação.
- Escapa textos OCR na página HTML, aplica CSP sem rede e usa URL de objeto apenas para vídeo escolhido pelo usuário. O vídeo não é incorporado ao pacote.
- Limite inicial de 64 candidatos e imagens de até 12 MiB cada. Uma fila maior deve ser dividida em lotes antes da visualização.
- A verificação de hashes **não** comprova interpretação OCR, autenticidade do vídeo, atribuição de jogador ou correção matemática. A prova de origem vídeo→ROI exige auditoria independente do ciclo 182/183.
- Equity, EV, identificação de ator e autorização de exportação de clipes continuam explicitamente desativados.

## Como executar

```bash
python video_analyzer/offline_action_review_triage.py TIMELINE.json TRIAGE.json
python video_analyzer/offline_triage_review_dashboard.py TIMELINE.json TRIAGE.json VIEWER_DIR NEW_DASHBOARD_DIR
# Abrir NEW_DASHBOARD_DIR/index.html em um navegador que permita arquivos locais.
python -m pytest -q video_analyzer/test_offline_triage_review_dashboard.py video_analyzer/test_offline_action_review_triage.py video_analyzer/test_offline_action_bet_timeline.py
```

`VIEWER_DIR` deve conter `action_roi_report.json` e as imagens `assets/roi_NNN.png` geradas pelo visualizador anterior. O arquivo de saída `manifest.json` inclui hashes SHA-256 do histórico, triagem, relatório, HTML e imagens. Não inclui gravação do usuário.

## Validação e bloqueios

Testes sintéticos locais: **68/68 aprovados** (18 novos e 50 regressões). Integração com fixture artificial de quatro mesas e oito candidatos. Chromium headless carregou a página via `set_content`, mostrou oito cartões e navegou para o segundo 4 de um MP4 artificial de nove segundos. A navegação direta via `file://` e `http://127.0.0.1` foi bloqueada pela política do ambiente; portanto não está validada no Windows nem no navegador aberto diretamente do disco.

Falta vídeo autorizado e anotado de 3–5 minutos para medir OCR e segmentação reais. Não foram executadas sessões reais de 40–60 minutos, cálculos de equity/EV, suíte completa do repositório nem GitHub Actions. Sem alterações em `main`, produção, credenciais ou gastos.
