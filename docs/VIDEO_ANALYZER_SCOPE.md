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

## Bloqueios e estado de validação
Falta vídeo real autorizado e anotado de 3–5 minutos para calibrar reconhecimento visual e medir a precisão de detecção de mãos, cartas, ações e OCR. A prova de conceito offline de ingestão, amostragem, mudança visual, refinamento temporal e OCR de ROIs possui testes **sintéticos** (ciclos 168–172), mas ainda não foi validada com sessões reais de 40–60 minutos. O texto OCR é apenas proposta sujeita à revisão humana; não é entrada automática de equity/EV. Testes completos no Windows e validação de ponta a ponta permanecem pendentes.
