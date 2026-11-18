# Cortador de Mãos PLO — somente gravações de vídeo

**Entrada principal: um único MP4 com a sessão completa** (ou, alternativamente, 2, 6 ou mais partes **consecutivas**, sem lacunas). O programa não usa DriveHUD, histórico TXT, banco de dados do poker nem conexão com a sala. Trabalha **offline**, após a sessão.

## Estado atual

Existe uma **primeira implementação de detecção visual + OCR**, ainda **não validada em gravações reais**. O novo aplicativo se chama **analise_video.py**; a interface legada **cortador.py** permanece no repositório somente como editor/cortador auxiliar. Ela ainda tem os recursos antigos de importação, mas **não são utilizados** pelo novo analisador.

### Fluxo implementado

1. Selecionar **um vídeo completo** ou múltiplos MP4 consecutivos.
2. Escolher a disposição das **quatro mesas**: `4 lado a lado` (padrão no vídeo do usuário; mesa 1 mais à esquerda, mesa 4 mais à direita) ou `2 por 2` (mesa 1 superior esquerda, 2 superior direita, 3 inferior esquerda, 4 inferior direita).
3. Preencha **Nick do jogador** (por padrão, `~Pulgar~`). O programa já traz **as regiões das cartas, do saldo e do nome pré-calibradas a partir do print**. O jogador principal fica na parte inferior de todas as mesas e é o único com cartas visíveis no pré-flop. As regiões podem ser corrigidas com o mouse se o layout mudar.
4. Em **Marcar região → nick** é possível ajustar a área roxa sobre o nome do jogador, se necessário. O botão **Verificar nick no frame** usa Tesseract OCR para testar se o nome foi reconhecido neste quadro. Não precisa mais registrar quadro sem cartas: a detecção usa a presença das cartas claras na região fixa do herói. O valor de 1 BB começa em **1**, porque a interface do print já exibe o stack em BB.
5. O analisador passa pelo **vídeo inteiro** em ordem, amostrando 1 quadro por segundo por meio de FFmpeg, e tenta reconhecer transições **sem cartas → cartas visíveis → sem cartas** em cada mesa separadamente.
6. Usa Tesseract OCR para estimar o saldo **antes e depois** da mão; seleciona prováveis quedas líquidas **de 30 BB ou mais (incluindo exatamente 30 BB)**, além das mãos com leitura inconclusiva.
7. Mostra a lista com horários da gravação, mesa e perda **estimada**, e permite conferir/editar os valores e os limites. Você também pode **incluir manualmente** mãos que o OCR não detectou e **salvar/abrir a revisão** em JSON para continuar mais tarde.
8. **Somente as mãos conferidas** com perda igual ou acima do limite são exportadas em **MP4 independentes**, recortadas na mesa correspondente, com início anterior às cartas e fim após a mão; gera também **indice_das_maos.csv**.

As configurações das regiões das quatro mesas podem ser salvas em JSON e reutilizadas. A revisão das mãos também pode ser salva em arquivo JSON, evitando ter de analisar o vídeo inteiro novamente depois de fechar o programa.

## Limitações (importante)

**A detecção não é garantida 100% e ainda não foi aferida em vídeos reais.** Valor do saldo e mudança do saldo observada no vídeo são evidências, não substituem um histórico completo. OCR pode errar números, esconder decimais ou não conseguir ler o valor. Rebuy, add-on, mudança de mesa, troca de posição do jogador, zoom, overlays, mesas menores e frames de animação de ficha/pote podem gerar alarmes falsos ou omissões. Se uma mão começar/terminar fora da gravação, deve ser revisada. A diferença de saldo antes/depois pode incluir o pagamento de blinds/apostas e também interferências de uma mão seguinte se a transição for muito rápida.

**A identificação pelo nick é auxiliar e experimental.** Na análise do vídeo, o Tesseract tenta confirmar o nick em algumas amostras iniciais de cada mesa e informa na tabela se houve correspondência. O nick também é salvo na configuração, no projeto e no CSV de exportação. Como o nome é pequeno e pode ficar encoberto pelas cartas, **uma leitura não confirmada NÃO elimina uma mão**, que continua identificada pela posição fixa do jogador e suas cartas visíveis no pré-flop. O campo `nick` pode ser calibrado manualmente sobre a tarja do nome caso o retângulo do print não se encaixe. Se a disposição das mesas mudar, analise o segmento separadamente após nova calibração.

A pre-calibração usa posições inferidas de um print, não coordenadas validadas frame a frame no MP4 completo. Imagens de cartas claras e elementos luminosos de interface podem confundir o detector, então confira os retângulos na prévia antes de analisar. Mãos em que as cartas do herói não aparecem de maneira confiável (ex.: cartas encobertas, exibição de cartas durante todo o vídeo) podem ser ignoradas. Mãos sem flop também são potencialmente detectáveis porque a detecção observa **cartas do herói**, não depende do board.

**Portanto não considere os recortes como conjunto completo auditado de todas as perdas sem revisar.** O limiar de 30 BB é **inclusivo (≥30)**. Não existe saldo inicial padrão de 100 BB: a perda líquida é calculada por `(saldo antes − saldo depois) / valor de 1 BB`. Portanto, 100→70, 150→120 e 200→170 são todos exemplos de perda de 30 BB; uma mão em que o jogador aposta 30 BB e recupera esse valor não entra como perda de 30 BB.

## Instalação automática guiada (mais fácil)

1. Baixe o ZIP da branch e abra a pasta `tools/cortador-maos-30bb`.
2. Dê dois cliques em **INSTALAR_TUDO_WINDOWS.bat**. Após pedir sua autorização, ele usa o **WinGet da Microsoft** para instalar Python 3.12, FFmpeg e Tesseract e tenta instalar Pillow. Pode haver pedido de aprovação do Windows (UAC).
3. Ao terminar, **feche e abra novamente** a pasta/terminal; execute **INICIAR_ANALISE_VIDEO.bat**.
4. Se o programa disser que não achou FFmpeg/Tesseract, reinicie o Windows e tente de novo. Se seu Windows Ghost Spectre não tiver WinGet, será necessário instalar o App Installer ou usar os links manuais abaixo.

O instalador **não foi testado neste Windows**; ele depende do WinGet e da conectividade. Não desative antivírus ou avisos de segurança para executá-lo.

## Instalação no Windows 10/11

Não precisa ter Git.

1. Abra a branch [feature/cortador-maos-30bb](https://github.com/erickmendespkr-maker/PLO-Trainee-/tree/feature/cortador-maos-30bb), clique em **Code > Download ZIP**, extraia os arquivos e entre em **tools/cortador-maos-30bb**.
2. Instale [Python 3.12 com Tkinter](https://www.python.org/downloads/windows/) (caso ainda não esteja instalado).
3. Instale [FFmpeg e FFprobe](https://ffmpeg.org/download.html) e deixe seus executáveis no PATH ou ao lado do script.
4. Instale [Tesseract OCR para Windows](https://github.com/UB-Mannheim/tesseract/wiki) com o idioma inglês. A instalação padrão em \`C:\Program Files\Tesseract-OCR\` é detectada pelo iniciador. O arquivo \`eng.traineddata\` deve estar na pasta \`tessdata\`.
5. Execute **INICIAR_ANALISE_VIDEO.bat**. O iniciador instala somente a dependência Python **Pillow** se faltar.

## Calibrar com as quatro mesas

**Seu vídeo é horizontal, com quatro janelas verticais lado a lado.** Confirme no topo **Disposição: 4 lado a lado** antes de calibrar. As linhas amarelas devem dividir a prévia em quatro colunas. Na versão antiga as linhas formavam quatro quadrantes e os MP4 saíam incorretos; esta atualização corrige o preview, o mapeamento e o recorte.

- Abra o vídeo e escolha uma **mesa** de 1 a 4.
- Preencha o campo **Nick do jogador**, por exemplo `~Pulgar~`. O nick é salvo na configuração e no relatório final. Confira as **regiões predefinidas em verde (cartas), azul (saldo) e roxo (nome)**. As quatro mesas estão alinhadas horizontalmente, com o herói na posição inferior.
- Só se necessário, use **Marcar região → cartas** para corrigir o retângulo das cinco cartas do herói (sem cobrir nome, mesa, apostas, timer ou mensagens).
- Só se necessário, escolha **saldo** e desenhe um retângulo bem justo sobre o valor numérico do saldo do herói.
- Para validar o nick, escolha um frame em que o nome esteja nítido; selecione a mesa e clique **Verificar nick no frame**. Se falhar, use **Marcar região → nick** e redesenhe sobre o texto do nome. Não é preciso confirmar o nick para iniciar a análise.
- **Não é necessário registrar referência sem cartas.** O programa procura as cartas claras nos retângulos predefinidos; pressione **Usar regiões do print** para restaurar todas as áreas, se necessário.
- Informe o valor de uma BB naquela mesa: exemplo fictício R$0,50/R$1,00 significa **1** (na mesma unidade do saldo). Se a interface exibe o saldo já em BB, coloque **1**.
- As quatro mesas já vêm configuradas. Confira se os retângulos cobrem corretamente suas cartas e saldos e, em seguida, salve a configuração.
- Clique **ANALISAR VIDEO(S)**; a detecção é automática, mas a precisão dos saldos do OCR e a classificação das perdas ainda dependem da revisão humana.
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

## Ajustar o quadro azul (saldo do jogador) e acelerar a análise

Se o retângulo **azul** não estiver exatamente sobre o **número do saldo em BB** do herói, o OCR pode ler o nick, cartas ou valores de outro jogador e gerar perdas erradas. Com o vídeo carregado:

1. Selecione **Mesa 1** e **Marcar região → saldo**.
2. Desenhe um novo retângulo azul bem justo sobre o **valor do saldo**, incluindo os algarismos e a vírgula decimal (e BB, se fizer parte do mesmo texto). Não inclua nickname nem fichas/apostas.
3. Ao soltar o mouse, a mesma posição relativa será **automaticamente replicada nas outras três mesas** quando estiver em `4 lado a lado`.
4. Clique **Testar saldo**; o número retornado pelo OCR deve corresponder ao saldo visível no vídeo. Ajuste novamente se for diferente.
5. Salve a configuração e só então inicie a análise. As regiões do print são aproximações e precisam ser validadas no seu vídeo.

A opção **OCR rápido** vem marcada por padrão. Ela conserva 1 quadro por segundo para detectar início/fim da mão, mas reduz os testes OCR de saldo de até três imagens por lado com duas passagens de leitura para até duas imagens por lado com uma passagem quando legível. Em caso de leitura totalmente falha, tenta outra imagem com o método detalhado. Desmarque **OCR rápido** para usar mais leituras nas mãos difíceis.

O OCR rápido pode perder precisão; antes de exportar os MP4, confira as mãos encontradas e seus saldos. O desempenho real depende do tamanho/resolução da gravação e do PC; não há promessa de ganho percentual específico. Não é necessário reinstalar as dependências, apenas atualizar os scripts do ZIP.
