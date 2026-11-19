# Fusao do rastreamento de fichas — PLO Cortes

## Origem analisada
Arquivo fornecido pelo usuario: `poker-data-scraper-main.zip`, da fonte
`Baivaras/poker-data-scraper` (GitHub). Foram inspecionados:

- `detection/action_detector.py`: distinguir quedas de stack, ruido de OCR,
  corroboracao por regiao das fichas apostadas e confirmacao entre quadros
- `detection/ocr.py`: leitura local por regioes de tela
- `detection/region_cache.py`: evitar analises repetidas de regioes estaticas
- `tracking/game_tracker.py`: persistir estado da mao apos o fold do Hero
- `test_game_tracker.py`: reproduzir gravacoes/quadros para testes de regressao

**Licenciamento:** a copia ZIP enviada nao continha LICENSE e o repositorio
nao apresentava uma licenca de reutilizacao expressa. Por isso, nenhum
arquivo de codigo do projeto externo foi incorporado literalmente. Os
mecanismos equivalentes abaixo sao implementacoes originais para o PLO
Cortes. A referencia e arquitetural; modelos treinados externos, componentes
de automacao e templates da sala PokerStars nao foram importados.

## O que foi integrado

- `rastreador_eventos.py`: transforma leituras repetidas do stack em
  eventos confiaveis de saida/entrada de fichas; detecta anomalias de rebuy
  ou devolucao e as envia para revisao
- `fold_local.py`: amplia a ROI acima/esquerda do HUD e compara o banner
  FOLD da captura enviada pelo usuario em multiplas escalas; usa OCR como
  complemento; roda offline, OpenCV opcional
- `analise_video.py`: procura FOLD em todas as maos, sem prefiltrar por BB;
  quando fold e detectado, combina leituras de stack existentes com novas
  leituras proximas ao fold e calcula o investimento liquido possivel
- `limites_maos.py`: preserva o MP4 ate a proxima distribuicao de cartas
  na mesma mesa, mesmo que Hero tenha desistido antes
- `testes_rastreador_eventos.py`, `testes_fusao_visual.py` e outras suites:
  cobrem queda de 42 BB, fold abaixo de 30 BB, rebuy, OCR espurio, regioes
  de Fold e persistencia do recorte

## Limites: o que nao podemos declarar como confirmado

1. Stack inicial/final sem eventos intermediarios nao prova perda se houve
   recompra automatica.
2. Aumento de stack no meio da mao pode representar devolucao ou rebuy.
   Sem distinguir visualmente, **nao marcar perda como confirmada**.
3. Sem Fold nem premio do pote observavel, deixar a mao pendente.
4. As suites unitarias nao substituem validar com os MP4 originais; o CSV
   com 38 maos nao contem os frames para demonstrar a taxa real de acerto.

## Como usar

1. Execute `INICIAR_ANALISE_VIDEO.bat`, que tenta instalar a dependencia
   OpenCV caso ainda nao esteja presente.
2. Para testes unitarios, execute `VERIFICAR_PROGRAMA.bat`.
3. Informe o limite de 30 BB e selecione a pasta de saida desejada.
4. Guarde `relatorio_analise.csv` para conferir
   `fold_ocr_melhor_confianca`, `fold_encontrado`, `instante_fold`,
   `eventos_stack_json`, `motivo_perda_bb` e `perda_bb`.

## Proximos criterios de aceitacao

- Todas as maos identificadas sao avaliadas pelo detector de Fold;
- Um fold real com investimento >=30 BB sem devolucao gera MP4 completo;
- Fold de 10 BB nao gera perda >=30;
- Rebuy de 100 BB nao se transforma automaticamente em perda;
- Uma mao sem prova de Fold ou premio vai para revisao, com evidencias;
- Multimesas: nunca estender um corte atraves da proxima mao da mesma mesa.
