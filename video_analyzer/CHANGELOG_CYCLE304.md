# PLO Trainee — ciclo 304 (12/11/2026)

## FEITO E TESTADO

- Publicados na branch autorizada: módulo Python de propostas de cartas comunitárias, 18 testes locais e layout de exemplo para quatro mesas. Hash Git dos dois arquivos de código e testes confrontado com os arquivos testados.
- FFmpeg extrai quadros offline; FFprobe valida metadados; showinfo registra PTS decodificado.
- Para cada mesa, cinco regiões de interesse do board medem a fração de fundo claro. Resultado heurístico: flop candidato (3), turn candidato (4), river candidato (5), nenhum board aberto detectado (0), ou ambíguo.
- Todos os resultados são não verificados. Mudanças entre amostras formam somente intervalos candidatos à revisão, jamais mãos ou ações reconstruídas.
- Proteções: SHA-256 de vídeo/layout, checagem de origem/PTS, ROIs e IDs, entrada JSON restrita, sem sobrescrever arquivos e sem acesso a plataformas de poker ao vivo.
- **18/18 testes locais passaram**, incluindo extração e PTS com FFmpeg em vídeo sintético, detecção de 0/3/4/5 cartas, ambiguidades, entradas inválidas, adulteração de layout e bloqueio de overwrite.

### Gravação real (privada, não publicada)

- O RAR fornecido esteve acessível e foi extraído localmente usando libarchive. MP4: **748.193.539 bytes, 3610,1 s (60min10s), 1730×800, 20 FPS, H.264**.
- Amostragem dos primeiros dois minutos: **12 instantes (5–115 s, passo 10 s), 48 observações de mesas e 16 intervalos candidatos de mudanças visuais**.
- Amostragem distribuída na sessão: **24 instantes (5–3455 s, passo 150 s), 96 observações de mesas e 60 intervalos candidatos**.
- Das 96 observações isoladas: **51 sem board face-up detectado, 24 flops candidatos, 12 turns candidatos, 7 rivers candidatos e 2 ambíguas**.
- **Os 60 intervalos não correspondem a 60 mãos nem a eventos confirmados**: vários acontecimentos podem ocorrer entre quadros espaçados por 150 segundos. Uma inspeção visual limitada de quatro timestamps indica ROIs plausíveis, não validação estatística.
- Nenhum vídeo, quadro, screenshot ou nome de usuário da gravação foi enviado ao GitHub.

## NÃO VERIFICADO

- Não existe ground truth humano formal para avaliar precisão, sensibilidade ou F1 do detector.
- Não foram identificados ranks/suits das cartas, ações, stacks, ranges ou mãos completas.
- A ausência de cards face-up não prova que a mão está preflop; cartas viradas para baixo ou sobreposições podem gerar confusão.
- Não houve equity/EV calculado para mãos reais nem corte estratégico aprovado.
- Não houve CI remoto; execução apenas local.

## PENDÊNCIAS MINHAS

1. Anotar 2–5 mãos reais com mesa, intervalo, cartas e apostas, e medir divergências do detector.
2. Integrar propostas de street, leitura OCR e revisão humana numa timeline sem inferir fatos ausentes.
3. Vincular a primeira mão revisada a equity Monte Carlo e EV condicionado a ranges.
4. Exportar corte MP4 com explicação auditável e separação explícita de observações e hipóteses.

## PRÓXIMO CICLO

Construir interface offline de revisão dos intervalos candidatos com quadros e PTS, validar contra anotações humanas e avançar para integração matemática.

### Execução

```bash
cd video_analyzer
python -m unittest -v test_offline_board_street_proposals
python offline_board_street_proposals.py VIDEO.mp4 board_layout_4table_1730x800.example.json NOVO_RELATORIO.json
```

A calibração é um exemplo por resolução/layout, não um detector genérico. Nenhuma alteração na main, produção, credenciais ou custos, nenhum uso de serviços/propriedade intelectual do PLO Mastermind.
