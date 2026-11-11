# PLO Trainee — Ciclo 277 (11/11/2026)

## FEITO E TESTADO
- Novo módulo `offline_real_probe_review_handoff.py` transforma propostas de presença de mesa e OCR de potes em **intervalos candidatos** para revisão humana. Consome o JSON de `offline_real_video_probe.py`; integra-se ao formato de requisições do exportador `offline_reviewed_clip_export.py`, mas mantém **`reviewer_confirmed_offline: false`** nos rascunhos.
- Proteções: SHA-256 dos bytes do vídeo, layout e relatório; timestamps monotônicos e variação relativa de PTS; IDs de mesas únicos; confidência OCR; validação de ROIs; bloqueio de reescrita; rejeição de relatório que se declare matematicamente autorizado.
- FFmpeg + FFprobe + Tesseract reais processaram **12 amostras** do vídeo PLO5 enviado pelo usuário, em segundos de reprodução `5,15,25,35,45,55,65,75,85,95,105,115` (primeiros dois minutos), com quatro regiões de mesa configuradas manualmente.
- Resultado do *detector heurístico*, **não ground truth**: as quatro regiões foram propostas como visíveis nas 12 amostras. O handoff gerou **21 eventos candidatos de mudança de OCR de pote** e **21 rascunhos de cortes não aprovados**. Estes números não representam 21 mãos.
- O relatório anterior, com cinco amostras dispersas pela sessão, gerou **8 eventos** e **3 rascunhos não aprovados** (intervalos distantes não ganham cortes automáticos).
- **25/25 testes locais aprovados**: dez regressões do probe de vídeo real e 15 novos testes do handoff. Incluem arquivo MP4 sintético codificado com FFmpeg, fonte adulterada, JSON duplicado, ambiguidade de timestamp, flags inseguras e bloqueio de overwrite.
- Confirmação dos hashes Git dos arquivos de código e testes contra os bytes testados localmente.

## NÃO VERIFICADO
- Nenhum desses eventos corresponde a uma mão reconstruída ou a uma ação comprovada. OCR e presença de mesa ainda não têm validação quantitativa com anotações manuais.
- Não foram produzidos novos diagnósticos de equity/EV de mãos reais nem cortes comentados estrategicamente; os rascunhos são somente **intervalos para inspeção**.
- Não há análise completa da sessão de 60 minutos ou teste de CI remoto/Windows neste ciclo.
- Não foi verificada, neste ciclo, a compatibilidade dos rascunhos com a execução integral do exportador de cortes (embora o esquema tenha os campos esperados).

## PENDÊNCIAS MINHAS
- Definir pelo menos 2–5 mãos rotuladas por pessoa (início/fim, cartas, board, ações, tamanho do pote) no vídeo gravado antes de medir precisão/atribuir erro.
- Não há necessidade de reenviar o vídeo para a execução local realizada neste ciclo; o arquivo original **não é incluído no repositório** e pode não estar disponível em futuras execuções.

## PRÓXIMO CICLO
1. Usar os trechos candidatos para anotação temporal de mãos reais, com PTS e ROIs associados à gravação.
2. Medir OCR contra revisão humana e registrar falsos positivos do detector de mesa.
3. Ligar mão confirmada + ranges declarados ao motor Monte Carlo/EV; exibir incertezas e impedir interpretações GTO não suportadas.
4. Exportar corte MP4 explicativo com hipóteses matemáticas vinculadas à mão revisada e sidecar auditável.

## Execução local
```bash
python -m unittest -v test_offline_real_video_probe test_offline_real_probe_review_handoff
python offline_real_probe_review_handoff.py VIDEO.mp4 LAYOUT.json PROBE.json NOVA_FILA.json
```

Sem alterações em `main`, produção, credenciais, integrações ao jogo em tempo real ou gastos. Dados privados, quadros reais e vídeo não foram publicados no GitHub.
