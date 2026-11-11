# PLO Trainee — Ciclo 276: primeiro vídeo real (offline)

## Escopo cumprido neste ciclo
- Recebido vídeo de sessão gravada PLO5 (MP4 extraído localmente de RAR; 3610,1 s, 1730x800, H.264, 20 FPS).
- Nenhum vídeo bruto, quadro real, imagem de jogador ou credencial foi enviado ao GitHub.
- Implementado `offline_real_video_probe.py`: amostragem FFmpeg/FFprobe com PTS, até quatro regiões manuais, proposta de presença de mesa por amostras RGB, OCR Tesseract de texto de pote e JSON revisável.
- Regiões e RGB são declarados; não há reconhecimento automático completo de mesas. Quando uma mesa deixa de estar visível, não é convertida automaticamente em uma mão.
- O módulo aceita gravações de até 3900 s (incluindo pequena cauda sobre 60min). O limite dos outros pipelines continua pendente de revisão; não declarar compatibilidade de ponta a ponta.

## Evidência verificada localmente
- Amostras de reprodução em **5, 60, 600, 1800, 3000 s**; PTS decodificado bateu com cada timestamp nessa gravação.
- Presença heurística dos quatro slots: **4, 4, 3, 4, 4**.
- **13** valores numéricos candidatos no OCR de pote. Valores são **não verificados**; a leitura de um dígito pode estar errada.
- **10 testes sintéticos aprovados** por `python -m unittest -v test_offline_real_video_probe`, incluindo MP4 sintético lido por FFmpeg e Tesseract, integridade de ROIs, não-sobrescrita do relatório, IDs repetidos e regiões sobrepostas.
- Um corte MP4 de **10 s** foi exportado localmente para demonstração; anotação informa que o EV não foi calculado. O corte não foi publicado no GitHub.

## Não verificado / limitações
- Não houve avaliação de acurácia contra rótulos humanos de cartas, ações, potes ou limites de mãos.
- As cinco amostras não abrangem todo o vídeo de 60 min; o código não reconstrói mãos.
- Nenhuma equidade Monte Carlo ou EV condicionado a ranges foi executado a partir do vídeo; OCR é evidência provisória, não fato.
- Ainda não foi demonstrado pipeline de ingestão integral, múltiplas mesas ao longo do tempo nem integração OCR→histórico estruturado→análise→clipes narrados.
- Testes Windows, CI remoto e reexecução após download do GitHub não foram realizados neste ciclo. Os blobs Git publicados foram conferidos por SHA contra os arquivos locais testados.

## Próximo ciclo
1. Pedir confirmação manual de um trecho curto com início/fim de mão e cartas visíveis para benchmark real com ground truth.
2. Ampliar a amostragem adaptativa e revisar transições de layout com evidência temporal, preservando limites de recursos.
3. Conectar as propostas revisadas ao histórico estruturado, mantendo equity/EV bloqueados sem dados e ranges suficientes.

Nenhum simulador jogável, bot, assistência ao vivo, integração externa, modificação de `main`, credenciais ou gasto adicional.
