# PLO Trainee — escopo revisado: análise de sessões gravadas

## Produto único
Usuário envia um vídeo gravado de uma sessão PLO5/PLO6 (até quatro mesas); a plataforma identifica mãos, estima qualidade matemática das decisões e devolve cortes com explicações. **Não** jogar, apostar ou interagir com mesas ao vivo.

## Pipeline de MVP
1. Upload local de MP4/WebM; validar formato, duração, resolução e limites; excluir arquivos após prazo configurável.
2. Extrair quadros por mudança de cena e intervalos adaptativos com FFmpeg; preservar timestamps e regiões das mesas.
3. Detectar mesas e acompanhar cada mesa ao longo do tempo; identificar cartas privadas *visíveis*, board, tamanho do pote, stacks e ações. OCR + visão computacional com confiança por campo.
4. Construir histórico estruturado por mão, incluindo incertezas; sinalizar mãos incompletas e permitir correção manual.
5. Calcular equity por Monte Carlo com regras Omaha (exatamente duas privadas e três comunitárias), intervalos de confiança e ranges adversários parametrizados.
6. Estimar EV de fold/call/raise conforme modelo de ranges, fold equity, tamanho de aposta e possíveis ações futuras. Não confundir equity com EV; não declarar erro definitivo quando dados insuficientes.
7. Priorizar mãos com impacto estimado maior e confiança suficiente; exportar MP4 dos cortes com timestamps, descrição e dados do cálculo.
8. Interface mínima: enviar vídeo, acompanhar processamento, revisar mãos incertas e baixar clipes/relatório.

## Primeiro marco técnico: prova de conceito
- Usar **um vídeo de exemplo autorizado** de 3–5 minutos com uma mesa.
- Extrair timestamps, identificar início/fim de mãos e registrar cartas/ações visíveis.
- Medir precisão de reconhecimento contra anotações humanas.
- Gerar um clipe e uma análise matemática com hipóteses explícitas.
- Só depois ampliar para quatro mesas e sessões de uma hora.

## Critérios de qualidade
- Não inferir cartas escondidas como fatos.
- Separar probabilidade observada, hipóteses de range e EV modelado.
- Reportar casos em que OCR ou identificação de ação é incerto.
- Registrar parâmetros, sementes e número de simulações para reprodutibilidade.
- Processar somente gravações enviadas pelo usuário; sem captura ou assistência em tempo real.

## Arquitetura proposta (a validar)
Frontend upload + fila de processamento + FFmpeg + reconhecimento visual/OCR + reconstrutor de mãos + motor PLO5/PLO6 + calculadora de equity/EV + gerador de cortes e relatório.
O Poker Kernel permanece como biblioteca de regras, não como interface do produto.

## Não incluído
Mesas jogáveis, adversários de IA para jogar, integração com plataformas de pôquer, decisões ao vivo, execução de apostas.

## Bloqueios e estado de validação (atualizado no ciclo 276)
Uma gravação autorizada foi fornecida pelo usuário como arquivo RAR: MP4 com 3610,1 segundos (60min10s), 1730×800, 20 FPS, PLO5; durante a gravação aparecem trechos com 3 e com 4 mesas. O **arquivo de vídeo e seus quadros não são publicados neste repositório**. Não há ainda um conjunto de anotações humanas por mão que permita medir acurácia de identificação de cartas, ações ou potes.

A prova de conceito `video_analyzer/offline_real_video_probe.py` foi executada localmente usando FFmpeg, FFprobe e Tesseract reais em cinco timestamps: 5, 60, 600, 1800 e 3000 segundos. As *propostas* de mesas presentes foram, respectivamente, 4/4/3/4/4. O OCR produziu 13 valores numéricos candidatos de pote entre 20 regiões potenciais, alguns potencialmente incorretos. O resultado **não** comprova reconstrução de mãos, cartas privadas, ações, equity, EV ou precisão de OCR.

O novo módulo foi testado com **10 testes sintéticos aprovados**, inclusive um MP4 sintético processado por FFmpeg + Tesseract. A origem PTS foi conferida nas cinco amostras da gravação real. Os dados reais não são fixture de CI e não devem ser enviados ao GitHub. A validação de todo o vídeo minuto a minuto, métricas contra anotações humanas e processamento de ponta a ponta ainda são pendências.

## Progresso de validação: ciclo 277 (11/11/2026)
- A gravação real permitiu uma amostragem adicional dos primeiros dois minutos: 12 quadros com FFmpeg/Tesseract em intervalos de 10 s, sem upload da gravação ao GitHub.
- `video_analyzer/offline_real_probe_review_handoff.py` cruza amostras do `offline_real_video_probe.py` com SHA de vídeo/layout, valida PTS e produz eventos **provisórios** entre amostras e rascunhos de cortes não aprovados.
- Foram detectadas 21 alterações candidatas de leitura de pote nas 12 amostras, gerando 21 rascunhos de revisão. **Não** são 21 mãos: o detector não comprova limites, cartas, ações, equity nem EV.
- Os 15 novos testes + 10 regressões do módulo anterior passaram localmente. A revisão humana de mãos reais e a acurácia dos reconhecedores continuam bloqueios. Consultar `video_analyzer/CHANGELOG_CYCLE277.md`.
