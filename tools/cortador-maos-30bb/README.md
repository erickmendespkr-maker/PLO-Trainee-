# Cortador de Mãos PLO — somente gravações de vídeo

**Entrada principal: um único MP4 com a sessão completa** (ou, alternativamente, 2, 6 ou mais partes **consecutivas**, sem lacunas). O programa não usa DriveHUD, histórico TXT, banco de dados do poker nem conexão com a sala. Trabalha **offline**, após a sessão.

## Estado atual

Existe uma **primeira implementação de detecção visual + OCR**, ainda **não validada em gravações reais**. O novo aplicativo se chama **analise_video.py**; a interface legada **cortador.py** permanece no repositório somente como editor/cortador auxiliar. Ela ainda tem os recursos antigos de importação, mas **não são utilizados** pelo novo analisador.

### Fluxo implementado

1. Selecionar **um vídeo completo** ou múltiplos MP4 consecutivos.
2. Identificar os **quatro quadrantes** (mesa 1: superior esquerda; 2: superior direita; 3: inferior esquerda; 4: inferior direita).
3. Configurar **uma única vez, por mesa**, a área pequena das **cartas do próprio jogador** e a área numérica do **saldo de fichas** (sem nome nem símbolos adicionais).
4. Em um quadro **sem cartas**, registrar a referência visual daquela área e informar o valor de **1 big blind em fichas**.
5. O analisador passa pelo **vídeo inteiro** em ordem, amostrando 1 quadro por segundo por meio de FFmpeg, e tenta reconhecer transições **sem cartas → cartas visíveis → sem cartas** em cada mesa separadamente.
6. Usa Tesseract OCR para estimar o saldo **antes e depois** da mão; seleciona prováveis quedas líquidas **estritamente superiores a 30 BB**, além das mãos com leitura inconclusiva.
7. Mostra a lista com horários da gravação, mesa e perda **estimada**, e permite conferir/editar os valores e os limites. Você também pode **incluir manualmente** mãos que o OCR não detectou e **salvar/abrir a revisão** em JSON para continuar mais tarde.
8. **Somente as mãos conferidas** e acima do limite são exportadas em **MP4 independentes**, recortadas na mesa correspondente, com início anterior às cartas e fim após a mão; gera também **indice_das_maos.csv**.

As configurações das regiões das quatro mesas podem ser salvas em JSON e reutilizadas. A revisão das mãos também pode ser salva em arquivo JSON, evitando ter de analisar o vídeo inteiro novamente depois de fechar o programa.

## Limitações (importante)

**A detecção não é garantida 100% e ainda não foi aferida em vídeos reais.** Valor do saldo e mudança do saldo observada no vídeo são evidências, não substituem um histórico completo. OCR pode errar números, esconder decimais ou não conseguir ler o valor. Rebuy, add-on, mudança de mesa, troca de posição do jogador, zoom, overlays, mesas menores e frames de animação de ficha/pote podem gerar alarmes falsos ou omissões. Se uma mão começar/terminar fora da gravação, deve ser revisada. A diferença de saldo antes/depois pode incluir o pagamento de blinds/apostas e também interferências de uma mão seguinte se a transição for muito rápida.

**O programa não identifica automaticamente o nick ~Pulgar~ pelo texto.** Você precisa marcar as cartas e o saldo desse jogador no vídeo de cada mesa. A calibração atual é fixa durante a gravação; se a disposição das mesas mudar, analise o segmento separadamente após nova calibração.

Mãos em que as cartas do herói não aparecem de maneira confiável (ex.: cartas encobertas, exibição de cartas durante todo o vídeo) podem ser ignoradas. Mãos sem flop também são potencialmente detectáveis porque a detecção observa **cartas do herói**, não depende do board.

**Portanto não considere os recortes como conjunto completo auditado de todas as perdas sem revisar.** O limiar de 30 BB é estrito (**>30**); perdas de exatamente 30 BB ficam de fora.

## Instalação no Windows 10/11

Não precisa ter Git.

1. Abra a branch [feature/cortador-maos-30bb](https://github.com/erickmendespkr-maker/PLO-Trainee-/tree/feature/cortador-maos-30bb), clique em **Code > Download ZIP**, extraia os arquivos e entre em **tools/cortador-maos-30bb**.
2. Instale [Python 3.12 com Tkinter](https://www.python.org/downloads/windows/) (caso ainda não esteja instalado).
3. Instale [FFmpeg e FFprobe](https://ffmpeg.org/download.html) e deixe seus executáveis no PATH ou ao lado do script.
4. Instale [Tesseract OCR para Windows](https://github.com/UB-Mannheim/tesseract/wiki) com o idioma inglês. A instalação padrão em \`C:\Program Files\Tesseract-OCR\` é detectada pelo iniciador. O arquivo \`eng.traineddata\` deve estar na pasta \`tessdata\`.
5. Execute **INICIAR_ANALISE_VIDEO.bat**. O iniciador instala somente a dependência Python **Pillow** se faltar.

## Calibrar com as quatro mesas

- Abra o vídeo e escolha uma **mesa** de 1 a 4.
- Use **Ir ao tempo global** para chegar a uma mão ou momento adequado.
- Em **Marcar região**, escolha **cartas** e desenhe um retângulo pequeno envolvendo somente as cartas do herói (sem cobrir nome, mesa, apostas, timer ou mensagens).
- Escolha **saldo** e desenhe um retângulo bem justo sobre o **valor numérico do saldo do herói**.
- Navegue até um instante em que o campo de cartas daquela mesa esteja **vazio**; clique em **Registrar referência SEM cartas**.
- Informe o valor de uma BB naquela mesa: exemplo fictício R$0,50/R$1,00 significa **1** (na mesma unidade do saldo). Se a interface exibe o saldo já em BB, coloque **1**.
- Repita nas quatro mesas. Salve a configuração.
- Clique **ANALISAR VIDEO(S)**; o tempo necessário depende do comprimento do vídeo e do hardware.
- Confira individualmente as perdas prováveis e os limites de tempo; use **Conferir/Salvar**. Se incorreto, **Descartar**.
- Clique **EXPORTAR CONFERIDAS** para gerar MP4 independentes com apenas a mesa escolhida.

**Por que conferir?** Um salto do saldo de 100 para 50 fichas não equivale necessariamente a uma perda de 50 BB sem a leitura contextual de apostas, rebuys e tempo de pagamento do pote. O OCR e os limites podem falhar, por isso a confirmação é obrigatória.

## Arquivos importantes

- \`analise_video.py\`: **aplicativo principal, somente vídeos**.
- \`INICIAR_ANALISE_VIDEO.bat\`: iniciador do aplicativo principal.
- \`cortador.py\`: componente de recorte FFmpeg e **editor legado**. Não precisa abrir este editor nem fornecer históricos.
- \`testes_visuais.py\`: verificações unitárias dos componentes visuais.
- \`INICIAR_NO_WINDOWS.bat\`: iniciador antigo do editor legado (não é o fluxo principal).
- \`GERAR_EXE_WINDOWS.bat\`: empacotamento antigo, **não** compila automaticamente o novo aplicativo.

## Privacidade e segurança

Executa localmente e não realiza interação em tempo real com a sala. É uma ferramenta para revisar **sessões encerradas**, não oferece orientação durante o jogo. O envio ao instrutor fica a seu critério.

## Testes

A implementação foi salva no GitHub, mas as ferramentas de execução local desta conversa estão com erro: **não foi possível executar testes Python nem validar a detecção e a exportação contra os seis vídeos fornecidos**. Execute \`py -3 testes_visuais.py\` após instalar Pillow e Tesseract. Esses testes unitários não substituem a validação com vídeos da sua interface.
