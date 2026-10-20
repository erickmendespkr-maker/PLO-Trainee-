# Auditoria do PokerTV — 20/10/2026

Fonte: https://github.com/BrunoPradoBR/pokertv (branch master), inspecionados pyproject.toml, models.py, segmenter.py, recognizer.py, state_machine.py, pipeline.py e árvore Git.

## Achados
- Python >=3.11, OpenCV, PyTorch/torchvision, PaddleOCR, mss; testes pytest declarados.
- Segmentação de regiões normalizadas por YAML; classificador ResNet18 de 53 classes (52 cartas + verso); OCR de pote/stacks; FSM para histórico de mãos.
- A FSM inicia preflop com **exatamente 2 cartas privadas** e grava `game_type="NLH"`; incompatível diretamente com PLO5/PLO6.
- Captura usa tela ao vivo (`mss`) e timestamps `datetime.now()`; vídeo gravado exige decodificação por FFmpeg/OpenCV, timestamps do arquivo, ordenação de quadros e rastreamento independente por mesa.
- `Pipeline` instancia **uma única** `HandStateMachine`; quatro mesas exigem estado isolado por `table_id`.
- Modelo treinado `models/card_recognizer.pt` é exigido no README, mas não apareceu na árvore; precisão em vídeos reais não foi demonstrada.
- **Nenhum arquivo LICENSE/COPYING foi encontrado na árvore do repositório.** Repositório público não significa autorização para copiar ou redistribuir código. Até esclarecer licença/permissão, usar apenas como referência arquitetural e escrever implementação original.

## Decisão
Preservar o repositório PLO Trainee e o motor AGPL existente; criar novo pipeline de vídeo original, isolado, com Python + FFmpeg/OpenCV para quadros, rastreamento por mesa, reconhecedor configurável e dados estruturados; reutilizar Poker Kernel apenas para regras/avaliação, sujeito a validação. Não copiar código/assets/modelos do PokerTV sem licença explícita.

## Primeiro entregável
Prova de conceito com vídeo de 3–5 minutos, uma mesa: frames com timestamps, região calibrada, eventos de início/fim de mão, JSON com campos incertos e um clipe MP4; depois expandir para quatro mesas. OCR e EV só devem ser avaliados após reconstrução confiável do histórico.

## Testes pendentes
Nenhum teste do PokerTV foi executado nesta auditoria. Falta vídeo real e validação de dependências/qualidade dos modelos.
