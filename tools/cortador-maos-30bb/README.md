# Cortador de Mãos PLO — somente gravações de vídeo

**Entrada principal: um único MP4 com a sessão completa** (ou, alternativamente, 2, 6 ou mais partes **consecutivas**, sem lacunas). O programa não usa DriveHUD, histórico TXT, banco de dados do poker nem conexão com a sala. Trabalha **offline**, após a sessão.

## NOVO: 1 RETANGULO VERDE POR MESA (HUD UNICO)

Conforme o exemplo enviado do video com **tres mesas lado a lado**, a interface agora mostra **somente uma caixa verde grande por mesa**, da parte inferior da area das cartas ate o final da barra de saldo. Ela inclui **cartas, nick e stack**. Nao se marcam mais tres retangulos separados.

- No video de 3 mesas, o perfil inicial e aproximadamente `[100,405,288,528]` na mesa 1, usando a imagem interna 960x540. Os retangulos equivalentes aparecem automaticamente nas mesas 2 e 3.
- Se quiser ajustar, selecione a mesa 1 e **arraste uma unica caixa verde** que cubra suas cartas, o nick e o saldo. O programa replica **a mesma posicao relativa** nas outras mesas daquele layout e salva o ajuste automaticamente no Windows.
- A deteccao de cartas e a leitura OCR do nick e do saldo usam **subareas internas calculadas pela geometria do HUD**. As subareas nao aparecem como retangulos extras. O Gemini continua sendo acionado apenas quando o OCR nao le saldos de forma suficiente.
- Perfis de **1, 2, 3 e 4 mesas** sao independentes. Uma caixa marcada em 3 mesas nao move as caixas do layout de 4.
- As caixas verdes grandes desenhadas na versao anterior usando o campo `cartas` (altura de 80 pixels ou mais na imagem interna) sao **migradas para HUD unico** ao carregar o arquivo `marcacoes_padrao.json`. Caixas antigas menores de cartas nao serao confundidas com o HUD inteiro.
- Para recarregar o desenho do exemplo, use **Usar regioes do print**. Para ajustar por cartas visiveis, use **AUTOAJUSTAR MARCACOES NESTE VIDEO**. Ajustes manuais permanecem prioritarios.
- Antes da analise de horas, selecione um frame no qual o saldo esteja visivel e clique **Testar saldo** para validar a faixa interna. A marca grande por si so nao garante que o OCR leia todos os numeros.

**Aviso:** esta e uma implementacao por heuristicas visuais. A deteccao de maos e de perdas liquidas >= 30 BB continua sujeita a erros quando as mesas mudam de posicao, as cartas sao encobertas ou os saldos ficam ilegiveis. Confirme os MP4 antes de enviar ao instrutor. Os testes de regressao foram adicionados, mas ainda precisam ser executados no PC com a gravacao real.

## Correção: saldo e nick buscados DENTRO do HUD verde inteiro

No teste da mesa 2, a janela de diagnóstico mostrava um recorte de **68 × 18 pixels** com o número cortado, apesar de haver um retângulo verde grande contendo cartas, nick e saldo. O motivo era uma subárea calculada em percentuais fixos. Isso também prejudicava a verificação do nick.

Nesta versão, **saldo e nick recebem o HUD completo**, exatamente como o usuário marcou. A partir desse recorte original, um novo módulo `hud_recognition.py` faz OCR procurando texto em diferentes regiões internas da própria caixa. Para o saldo, dá preferência ao número com a unidade **BB**, reduzindo confusão com números das cartas, pote e botões. Para o nick, examina várias linhas no HUD e procura o nome esperado.

O botão **Testar saldo** deve agora mostrar uma imagem grande contendo **cartas, nick e saldo simultaneamente**, em vez de apenas uma tira com um número parcialmente visível. As leituras brutas ficam abaixo para diagnosticar erros. O botão **Verificar nick no frame** usa a imagem original do HUD. Se o OCR local falhar e o Gemini estiver ativado, pode solicitar a leitura de nick e saldo em uma chamada. **Testar Gemini no frame** também envia o HUD completo e apresenta os dois campos identificados.

Durante a varredura de mãos, as amostras locais de saldo, o fallback do vídeo em resolução original e os recortes enviados ao Gemini passam a usar a **mesma caixa verde grande**. A área interna das cartas permanece separada para detectar início e fim da mão; você continua fazendo apenas uma marcação manual por mesa.

**Como validar:** baixe o ZIP atualizado, execute `VERIFICAR_PROGRAMA.bat` (inclui testes de leitura de HUD sem API), abra o vídeo de 13 minutos, selecione mesa 2 e clique `Testar saldo`. Confirme que a imagem do diagnóstico contém o HUD inteiro. Em seguida, clique `Verificar nick no frame` e, se necessário, `Testar Gemini no frame`. Nenhuma posição antiga deve ser utilizada para o OCR de saldo/nick nos layouts lado a lado.

O resultado ainda é **experimental**: Tesseract e Gemini podem falhar ou ler números incorretos. Perdas iguais ou maiores que 30 BB devem ser confirmadas em múltiplos quadros antes da exportação automática. A mudança de leitura não equivale a comprovar a precisão com sua gravação real.

## Estado atual

Existe uma **primeira implementação de detecção visual + OCR**, ainda **não validada em gravações reais**. O novo aplicativo se chama **analise_video.py**; a interface legada **cortador.py** permanece no repositório somente como editor/cortador auxiliar. Ela ainda tem os recursos antigos de importação, mas **não são utilizados** pelo novo analisador.

### Fluxo implementado

1. Selecionar **um vídeo completo** ou múltiplos MP4 consecutivos.
2. Escolher a **quantidade de mesas e disposição**: `Automatico (1 a 4 mesas)`, `1 mesa`, `2 lado a lado`, `3 lado a lado`, `4 lado a lado` ou `2 por 2`. Uma mesma sessão pode passar de 4 para 3, 2 ou 1 mesa.
3. Preencha **Nick do jogador** (por padrão, `~Pulgar~`). O programa já traz **as regiões das cartas, do saldo e do nome pré-calibradas a partir do print**, adaptando as coordenadas das janelas quando o usuário seleciona 1, 2 ou 3 colunas. O jogador principal fica na parte inferior de todas as mesas e é o único com cartas visíveis no pré-flop. As regiões podem ser corrigidas com o mouse se o layout mudar.
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

## Calibrar as mesas visíveis (1 a 4)

**Exemplo do print:** quatro mesas lado a lado. Para outras gravações, selecione **Disposição: Auto (ate 4, slots fixos)** quando as janelas mantêm as mesmas posições, ou escolha **1 mesa**, **2 lado a lado**, **3 lado a lado** ou **4 lado a lado** quando as janelas ocupam toda a tela. As linhas amarelas acompanham o layout selecionado. Para mudanças durante o vídeo, use **Registrar mudanca** no tempo correspondente.

- Abra o vídeo e escolha uma **mesa** de 1 a 4.
- Preencha o campo **Nick do jogador**, por exemplo `~Pulgar~`. O nick é salvo na configuração e no relatório final. Confira as **regiões predefinidas em verde (cartas), azul (saldo) e roxo (nome)**. As quatro mesas estão alinhadas horizontalmente, com o herói na posição inferior.
- Só se necessário, use **Marcar região → cartas** para corrigir o retângulo das cinco cartas do herói (sem cobrir nome, mesa, apostas, timer ou mensagens).
- Só se necessário, escolha **saldo** e desenhe um retângulo bem justo sobre o valor numérico do saldo do herói.
- Para validar o nick, escolha um frame em que o nome esteja nítido; selecione a mesa e clique **Verificar nick no frame**. Se falhar, use **Marcar região → nick** e redesenhe sobre o texto do nome. Não é preciso confirmar o nick para iniciar a análise.
- **Não é necessário registrar referência sem cartas.** O programa procura as cartas claras nos retângulos predefinidos; pressione **Usar regiões do print** para restaurar todas as áreas, se necessário.
- Informe o valor de uma BB naquela mesa: exemplo fictício R$0,50/R$1,00 significa **1** (na mesma unidade do saldo). Se a interface exibe o saldo já em BB, coloque **1**.
- As regiões de até quatro mesas vêm inicialmente configuradas a partir do print, mas **só as mesas visíveis entram no processamento** no modo Auto. Confira as caixas do saldo e das cartas para a quantidade de janelas presente. Salve a configuração.
- Clique **ANALISAR VIDEO(S)**; a detecção é automática, mas a precisão dos saldos do OCR e a classificação das perdas ainda dependem da revisão humana.
- Confira individualmente as perdas prováveis e os limites de tempo; use **Conferir/Salvar**. Se incorreto, **Descartar**.
- Clique **EXPORTAR CONFERIDAS** para gerar MP4 independentes com apenas a mesa escolhida.

**Por que conferir?** Um salto do saldo de 100 para 50 fichas não equivale necessariamente a uma perda de 50 BB sem a leitura contextual de apostas, rebuys e tempo de pagamento do pote. O OCR e os limites podem falhar, por isso a confirmação é obrigatória.

## Arquivos importantes

- \`analise_video.py\`: **aplicativo principal, somente vídeos**.
- \`INICIAR_ANALISE_VIDEO.bat\`: iniciador do aplicativo principal.
- \`cortador.py\`: componente de recorte FFmpeg e **editor legado**. Não precisa abrir este editor nem fornecer históricos.
- `testes_visuais.py`: verificações unitárias dos componentes visuais.
- `DIAGNOSTICAR_MESAS_WINDOWS.bat`: abre o diagnóstico automático do vídeo completo.
- `diagnostico_mesas.py`: cria os relatórios CSV de detecção e mudanças.
- `VERIFICAR_PROGRAMA.bat`: verifica sintaxe e executa testes sintéticos localmente.
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

## Novidade: mesas variáveis na gravação

**Não existe mais exigência de quatro mesas em todos os vídeos.** O modo inicial é **Automatico (1 a 4 mesas)**. Ele tenta inferir se o vídeo mostra uma, duas, três ou quatro janelas lado a lado e acompanha mudanças de disposição ao longo da gravação, inclusive quando as mesas são redimensionadas. A inferência usa repetição visual e divisórias entre janelas; em dúvida, interrompe temporariamente a avaliação em vez de considerar o desaparecimento de uma mesa como perda. Você pode conferir a detecção com **Conferir mesas no frame**.

- **Vídeo já começa com três mesas expandidas para preencher a tela:** escolha **3 lado a lado** em `Disposicao` antes de iniciar.
- **Quatro mesas e depois três sem reorganizar as posições** (uma janela some e fica um espaço vazio): mantenha **Automatico (1 a 4 mesas)**. Ele tenta preservar a grade original e ignorar o espaço vazio.
- **Quatro mesas e, em determinado instante, as três restantes são redimensionadas para preencher a tela:** o modo automático tenta identificar essa mudança sozinho. Se detectar de maneira incorreta, navegue até o instante da reorganização no campo **Ir ao tempo global**, escolha **3 lado a lado** em **Mudanca de mesas no tempo acima** e pressione **Registrar mudanca**. A linha do tempo manual e os layouts detectados são armazenados na revisão.
- **Vídeo com uma ou duas mesas já no início:** escolha **1 mesa** ou **2 lado a lado**, conforme a imagem.
- O botão **Conferir mesas no frame** informa quantos slots parecem ter mesas naquele quadro, para facilitar a verificação.

O analisador acompanha a disposição informada a cada segundo. Se uma mesa desaparecer ou o layout mudar durante uma mão, o trecho em aberto fica **inconclusivo** para revisão, em vez de ser lançado como perda de 30 BB. As mãos conferidas são exportadas com o recorte do layout identificado naquele trecho (1, 2, 3 ou 4 colunas). A configuração de pré-calibração do print é transformada horizontalmente; confira as regiões de cartas e saldo em cada mudança de tamanho.

**Limite importante:** a detecção automática de quantidade/disposição usa heurísticas visuais (padrões repetidos, bordas e estabilidade temporal), não um detector treinado para identificar janelas de poker. Ela pode reconhecer algumas mudanças de tamanho, mas não é confiável para janelas sobrepostas ou movimentos arbitrários. Se o detector errar, registre manualmente o tempo e o novo layout. A assinatura pode falhar com temas de mesa diferentes, overlays, janelas sobrepostas ou área de trabalho complexa; use a conferência no frame. A identificação de perdas também depende do OCR e continua experimental, sem garantia de recuperar todas as mãos relevantes.

O campo do limite permanece **30 BB inclusivos**: qualquer stack inicial (por exemplo, 75, 100, 150 ou 200 BB) é aceito. Só conta a queda líquida do stack antes/depois, não o valor apostado.

**Dica:** no modo Auto, a presença da mesa precisa satisfazer uma assinatura visual mais rigorosa; nos modos explícitos 1 a 4, a verificação é mais tolerante com temas diferentes. Em qualquer modo, se uma janela for removida ou o vídeo receber uma sobreposição, o algoritmo pode falhar. Confirme um quadro por meio do botão da interface antes de executar uma análise longa.

### Modo automático atualizado (experimental)

A interface abre em **Automatico (1 a 4 mesas)**, sem exigir seleção prévia de quantidade. Ao carregar um vídeo, o botão **Conferir mesas no frame** usa a inferência visual para apresentar o layout estimado e uma pontuação de confiança. Durante a análise integral, o programa espera três quadros consistentes antes de aceitar uma nova disposição, evita leitura de saldo na transição e registra os modos detectados na revisão JSON. Depois de conferir os resultados, a exportação usa o layout que foi salvo para cada mão, e não o número de mesas do início da sessão.

**Atenção:** o reconhecimento é uma primeira implementação, **não foi validado com o vídeo real do usuário e não passou por uma execução completa de testes neste ambiente**. Se a inferência ficar ambígua ou nenhuma mesa for detectada, é necessário escolher um layout explícito ou registrar a mudança manualmente. A área das cartas e do saldo foi estimada do print e precisa ser verificada, sobretudo após mudanças no tamanho das janelas. A perda mínima permanece **30 BB inclusivos**, calculada a partir do saldo real antes/depois de cada mão, não de um stack padrão de 100 BB.

## Diagnóstico automático de mesas (sem OCR)

Quando o vídeo tem 4 mesas e depois 3, 2 ou 1, use **DIAGNOSTICAR_MESAS_WINDOWS.bat** antes de iniciar a análise inteira. Ele abre uma janela para selecionar o **MP4 completo** e outra para salvar o CSV. Também é possível arrastar um MP4 sobre o arquivo BAT.

O diagnóstico utiliza FFmpeg e Pillow e examina aproximadamente **um quadro a cada cinco segundos**, sem ler saldos e sem usar Tesseract. Ele gera:

- **diagnostico_mesas_NOME.csv** — horário aproximado, layout candidato, disposição confirmada após três amostras, número aproximado de mesas visíveis e estado da detecção;
- **diagnostico_mesas_NOME_mudancas.csv** — momentos em que o detector confirmou uma nova disposição.

Os tempos representam **amostras**, não o segundo exato da mudança, e as pontuações são heurísticas — não são probabilidades de acerto. Se aparecer `INDEFINIDO`, confirme a imagem naquele horário e use uma disposição explícita ou registre manualmente a mudança no analisador. Não use o diagnóstico como prova de que todas as mesas ou mãos foram encontradas.

Se quiser validar o programa sem conhecimentos de programação, execute **VERIFICAR_PROGRAMA.bat**: ele checa a sintaxe Python e roda os testes visuais sintéticos. Esses testes não substituem verificar uma gravação real. Você já tendo instalado Python, Pillow e FFmpeg, não precisa reinstalá-los.

**Proteção de mãos nas transições:** o scanner não encerra a mão por um único frame ambíguo. Ele tolera breves interrupções (até alguns frames) e, se a mudança persistir ou for confirmada, marca a mão interrompida como inconclusiva em vez de inventar uma perda. Assim, após uma mudança de 4 para 3 mesas, o trecho suspeito deve ser revisado antes de exportar.


## Correção: selecionar perdas de verdade e gerar MP4 automaticamente

Na versão anterior, o programa misturava centenas de casos **INCONCLUSIVO - OCR** com perdas reais, e o botão **EXPORTAR CONFERIDAS** exigia validar manualmente cada mão antes de gerar qualquer arquivo. Isso não atendia ao fluxo de receber os cortes automaticamente. O OCR ainda podia concatenar números diferentes (por exemplo, interpretar um saldo como **154020 BB**) e criar perdas impossíveis.

A nova versão modifica o processo:

1. **Gerar MP4 automaticos** vem marcado por padrão. Ao clicar em **ANALISAR VIDEO(S)**, escolha a pasta de saída. O programa analisa a gravação, identifica somente **perdas líquidas de pelo menos 30 BB** e inicia a exportação dos MP4 automaticamente ao final.
2. **Só são exportadas automaticamente perdas com leituras OCR repetidas e coerentes**, obtidas antes e depois da mão. O valor inicial do saldo é variável (100, 150, 200 BB ou outro), sem exigir buy-in fixo.
3. A caixa **Mostrar OCR inconclusivo** vem desmarcada. Na lista principal, as mãos com ambos os saldos ilegíveis ficam ocultas; elas continuam registradas no relatório, sem serem confundidas com perdas.
4. O programa gera **indice_das_maos.csv** com os vídeos exportados, os saldos e as perdas estimadas, mais **relatorio_analise.csv** com os casos não confirmados e as falhas de leitura.
5. Se nenhuma perda passar pelo filtro de qualidade, o programa informa **zero cortes exportáveis** e orienta a corrigir o **retângulo azul**. Ele não gera vídeos de mãos incertas como se fossem perdas comprovadas.
6. **EXPORTAR PERDAS** continua disponível para salvar novamente as perdas identificadas ou mãos conferidas manualmente. A confirmação manual é opcional para a exportação das perdas com OCR consistente.

**Antes de reprocessar um vídeo de horas:** clique em **Testar saldo** com o frame carregado para conferir o valor exibido na tela. O programa também faz uma pré-verificação simples das caixas azuis no quadro inicial e alerta se nenhuma leitura for válida. Uma caixa azul posicionada sobre o nick, cartas ou apostas continuará provocando falhas, mesmo com a exportação automatizada.

**Proteções:** valores de saldo acima de **5.000 BB** são tratados como suspeitos e rejeitados pelo detector automático para evitar erros grosseiros do OCR; isso NÃO é uma referência de stack inicial (100 BB jamais é assumido). É um limite de segurança de leitura, sujeito a ajuste futuro para jogos com stacks excepcionalmente profundos. O critério de perda continua **30 BB inclusivos**, independentemente do saldo com que o jogador começou a mão.

**Estado da validação:** código atualizado e testes novos adicionados, porém os testes ainda não foram executados no Windows do usuário nem contra o vídeo completo real. OCR pode produzir falso positivo mesmo com duas leituras semelhantes. Revise os MP4 gerados antes de enviar ao instrutor. Para diagnosticar erros, envie o arquivo \`relatorio_analise.csv\` e uma captura onde as caixas azuis apareçam sobre os saldos.

## Testar saldo com a resolução original — correção de OCR

Se a região azul estiver correta e o programa ainda mostrar **Saldo não reconhecido**, a causa pode ser a redução da gravação para 960×540 usada pela varredura visual. Os números do stack ficam pequenos demais para o Tesseract, e aumentar uma imagem já reduzida não recupera os pixels perdidos.

Na versão atualizada:

1. Com o vídeo carregado e a região de saldo marcada, clique **Mostrar frame** no momento em que o saldo estiver legível.
2. Selecione a mesa e pressione **Testar saldo**. Agora o programa extrai somente aquela área diretamente do MP4 **na resolução original**, sem reduzir o quadro completo.
3. Uma janela de diagnóstico apresenta o **recorte original ampliado**, o saldo reconhecido (se houver) e as **leituras brutas** de várias preparações de imagem e modos do Tesseract.
4. Se o número continuar ilegível, pressione **Salvar recorte PNG** na janela e envie o arquivo `saldo_mesa_1.png` com um print das leituras brutas. Assim poderemos corrigir o filtro de reconhecimento específico do texto da gravação sem pedir o vídeo inteiro.
5. Durante a análise longa, se a leitura dos saldos na versão reduzida falhar, o programa tenta novamente os momentos anteriores e posteriores à mão com os **pixels originais da gravação**. Essa etapa extra só roda em trechos com OCR ausente/fraco, para não sobrecarregar todas as mãos.

O retângulo correto precisa mostrar **somente o número do saldo, e a unidade BB se estiver na mesma linha**. Se a janela ampliada revelar nick, aposta, cartas, ícones, saldo de outro jogador, ou um texto cortado, redesenhe a região de saldo e repita o teste.

**Observação:** o fallback em resolução original melhora a chance de reconhecimento, mas exige leitura adicional do vídeo e pode aumentar o tempo total. Não há garantia de identificação de todas as perdas: o programa ainda rejeita OCR duvidoso e não gera MP4 automaticamente a partir de números não verificados.

## Guardar as marcacoes como padrao (novo)

O programa agora guarda as regioes calibradas pelo usuario em um perfil permanente. O botao **Salvar como padrao** grava exatamente as caixas atuais de **cartas (verde)**, **saldo (azul)** e **nick (roxo)** das quatro posicoes, com o nick e o valor de 1 BB por mesa. Ao abrir a versao atualizada do programa, esse padrao sera carregado automaticamente. O botao **Usar padrao salvo** permite restaurar as marcas caso voce as altere por acidente.

O arquivo e gravado em `%LOCALAPPDATA%\\CortadorPLO\\marcacoes_padrao.json`, **fora da pasta ZIP/GitHub**, para que as marcacoes persistam entre atualizacoes e entre gravacoes. O arquivo salva somente a calibracao, nao o video e nao os horarios de mudanca das mesas.

**Se o programa antigo ja esta aberto e com os retangulos corretos (como no print enviado), nao feche sem salvar:** clique nele em **Salvar configuracao** e escolha um nome como `minhas_marcacoes.json`. Em seguida, abra o programa atualizado, clique **Abrir configuracao**, escolha esse JSON e so entao clique **Salvar como padrao**. Assim o perfil captura as coordenadas exatas do que foi desenhado na versao antiga, sem precisar calibrar novamente. O print isolado nao registra essas coordenadas numericamente.

**Cuidado:** **Usar regioes do print** restaura a estimativa de fabrica, e nao os ajustes pessoais. Para voltar aos ajustes pessoais, use **Usar padrao salvo**. O padrao pode ser sobrescrito quando voce clicar **Salvar como padrao** de novo; por isso confira a previa. Mesas reorganizadas de forma diferente ainda podem precisar de revisao visual das caixas.


## Integração Gemini no backend local (opcional)

O programa continua sendo um aplicativo de Windows com **backend Python local**. A API do Google Gemini atua somente como **segunda leitura visual** quando o Tesseract não confirma os saldos. A detecção de mesas, início e fim das mãos permanece local. Não são enviados vídeos completos: cada requisição de verificação contém até **quatro pequenos recortes do saldo** (dois antes, dois depois) e instruções para retornar apenas os quatro números, sem adivinhar.

### Primeira configuração segura

1. Crie uma **chave NOVA** em `https://aistudio.google.com/api-keys`. Se já compartilhou uma chave em mensagens, **revogue-a** e gere outra; não reutilize a chave exposta.
2. Abra `INICIAR_ANALISE_VIDEO.bat` da versão nova. Na faixa `Gemini quando OCR falhar`, clique em **Configurar chave**.
3. Cole a nova chave no campo oculto. O Windows protegerá a credencial com **DPAPI** no arquivo `%LOCALAPPDATA%\CortadorPLO\gemini_credencial.dpapi`, acessível no mesmo perfil do Windows. **Não é necessário criar .env nem colar a chave no GitHub.**
4. Escolha o modelo (por padrão `gemini-3.5-flash-lite`), marque **Gemini quando OCR falhar** e mantenha o limite inicial de **40 chamadas por análise**. É possível ajustar de 1 a 300.
5. No vídeo, selecione uma mesa e um frame com saldo visível, clique em **Testar Gemini no frame** e compare o número lido com o saldo real. Esse teste envia um único recorte e consome uma chamada de API.
6. Clique em **ANALISAR VIDEO(S)**. Quando o OCR local falhar, o Gemini tentará ler dois instantes distintos anteriores e dois posteriores à mão. Somente se cada par apresentar valores coerentes, a mão poderá ser considerada para corte. O filtro continua sendo **perda líquida de pelo menos 30 BB**, sem saldo inicial fixo.

As configurações JSON contêm apenas preferências, modelo e limite; **jamais contêm a chave**. Para configurações avançadas, também é possível fornecer `GEMINI_API_KEY` como variável de ambiente do processo, substituindo o arquivo DPAPI. O backend nunca imprime a chave nos logs, relatórios CSV ou nomes dos cortes.

### Privacidade, limites e verificação

- O uso do Gemini é **desligado até ser autorizado pelo usuário**. A leitura local continua funcionando sem conexão.
- A cota de 40 chamadas é um limite **deste programa**, não uma garantia de que a API seja gratuita: no plano pago do Google, chamadas podem ser cobradas. No plano gratuito, os limites e a disponibilidade variam.
- Ao ativar Gemini, recortes de imagens da sessão são enviados aos servidores do Google, sujeitos aos termos de tratamento de dados do plano usado.
- Se a API retornar 401/403/429 ou esgotar o limite local, o programa encerra as tentativas de IA e mantém leituras inconclusivas para revisão. Não marca uma perda somente por uma imagem.
- Leituras concordantes da IA ainda podem estar erradas; **confira todos os MP4 antes de enviar ao instrutor**. Os relatórios `indice_das_maos.csv` e `relatorio_analise.csv` identificam `origem = Gemini` ou `OCR`.
- Para testar o código **sem usar a chave e sem chamadas reais**, execute `VERIFICAR_PROGRAMA.bat`: ele executa `testes_visuais.py` e `testes_gemini.py`, usando respostas simuladas.

O programa não sincroniza nem administra a chave em uma plataforma web. Esta integração é o backend Python da versão desktop, sem hospedagem adicional.


## Correção da execução anterior que encontrou 0 cortes (18/11/2026)

A execução que mostrou centenas de ocorrências **INCONCLUSIVO - OCR** e nenhum MP4 não demonstrou que o jogador não perdeu 30 BB. Demonstrou que a análise não obteve duas leituras válidas antes e depois da mão. Foi encontrado também um problema no detector automático: quando as quatro mesas exibiam cartas, apostas e saldos diferentes, a semelhança visual caía e o programa podia classificá-las como uma única mesa.

**Correções deste pacote:** a detecção automática de 2, 3 ou 4 mesas agora considera divisórias estruturais verticais, mesmo com cartas diferentes; o OCR tolera espaços após vírgulas decimais; a leitura do saldo após a mão observa até seis quadros para acompanhar a estabilização do pote; e as ocorrências novas registram os instantes reais de leitura no arquivo JSON de revisão.

O novo botão **REANALISAR MAOS INCONCLUSIVAS COM GEMINI** permite aproveitar candidatos com OCR inconclusivo sem revarrer toda a gravação. Ele consulta recortes de dois instantes antes e dois depois da mão. Só seleciona uma perda de 30 BB ou mais quando a leitura é coerente; não transforma casos duvidosos em MP4 confirmados. A IA pode errar, então confira os cortes antes de enviar ao instrutor.

### Como recuperar a execução anterior

**Se a janela antiga continua aberta** com os resultados, clique em **Salvar revisão** e guarde um arquivo JSON antes de fechá-la. Abra a versão atualizada, use **Abrir revisão**, escolha o JSON, configure uma chave Gemini nova e pressione **REANALISAR MAOS INCONCLUSIVAS COM GEMINI**. Com **Gerar MP4 automaticos** marcado, escolha a pasta em que os cortes recuperados serão gravados.

**Se a execução anterior foi fechada sem salvar a revisão JSON**, os horários das mãos não foram guardados automaticamente. Será necessário analisar a gravação novamente na versão atualizada.

O limite de 40 chamadas cobre no máximo 40 ocorrências por rodada. Você pode repetir a reanálise para outras pendências; **salve a revisão JSON após cada lote** para conservar o registro de quais já foram consultadas e evitar repetir chamadas. Consulte sua cota da API: um projeto pago pode gerar cobranças.

O programa ainda depende de detectar corretamente as transições das mãos e pode deixar de reconhecer perdas em vídeos com mesas móveis ou imagens ilegíveis. Os testes adicionados usam respostas simuladas; não substituem a validação com a gravação original.


### Salvamento automatico da ultima revisao

A partir desta atualizacao, **toda analise concluida salva automaticamente** o arquivo de recuperacao em **%LOCALAPPDATA%\\CortadorPLO\\ultima_revisao.json**, mesmo se nenhuma perda for exportada. Uma reanalise Gemini concluida tambem atualiza essa ultima revisao, preservando os itens ja consultados e a quantidade pendente.

Na proxima abertura, clique em **Abrir ultima revisao**. Para enviar a revisao a outra pessoa ou fazer backup manualmente, use **Salvar revisao** e escolha um JSON. A ultima revisao e local, contem os caminhos dos videos do computador e nao envia nenhuma chave de API.

Este salvamento foi implementado agora; **nao pode recuperar retroativamente uma execucao antiga fechada sem salvar**.


## Ajustes de marcacao independentes para 1, 2, 3 e 4 mesas

**Problema corrigido:** marcacoes feitas numa gravacao de 3 mesas nao devem sobrescrever os retangulos da gravacao de 4 mesas. Antes, o programa convertia qualquer ROI manual para a grade antiga de quatro colunas e reaproveitava a mesma coordenada para videos diferentes; nick e saldo ficavam deslocados.

Agora cada disposicao possui suas proprias regioes de **cartas (verde)**, **nick (roxo)** e **saldo (azul)**. Ao abrir um video com 3 mesas, o programa tenta adaptar as caixas do perfil antigo, mas se voce corrigir algum retangulo, o ajuste sera usado **apenas no layout de 3 mesas**, mantendo intacto o perfil de 4. O ajuste de uma mesa pode ser replicado para as outras janelas do **mesmo layout**, sem assumir sempre quatro mesas.

**Salvamento automatico:** toda vez que voce arrasta e solta uma regiao, o programa tenta salvar a calibracao completa em `%LOCALAPPDATA%\CortadorPLO\marcacoes_padrao.json`. No proximo video com a mesma disposicao, ela ja aparece na posicao ajustada. O botao **Usar padrao salvo** tambem restaura o arquivo. O programa nao sabe identificar com certeza a posicao do saldo em um novo tema/layout; confira uma vez com **Mostrar frame** e **Testar saldo** antes de uma gravacao longa.

Ao trocar de video, o modo Auto agora limpa a inferencia visual do video anterior, e o campo de tempo volta ao inicio quando os videos sao limpos.

## Ativacao da chave Gemini em um clique (sem repetir a cada analise)

A chave compartilhada em uma conversa **nao pode ser instalada no Windows remotamente** e nao deve ser embutida no GitHub, pois ficaria exposta. Por seguranca, **revogue a chave enviada no chat e gere outra no Google AI Studio**.

Na versao atualizada, voce pode fazer uma unica ativacao local:

1. Copie a **nova chave** no AI Studio com Ctrl+C.
2. Abra o Cortador PLO e clique **Ativar chave copiada**.
3. Confirme a importacao. A chave e salva de modo protegido no seu perfil Windows, e a copia da area de transferencia e limpa.

Apos isso, o Gemini passa a ser detectado automaticamente nas proximas aberturas do programa, sem solicitar a chave novamente. O botao antigo **Configurar chave** continua disponivel como alternativa. Se voce desmarcar **Gemini quando OCR falhar**, o programa respeita essa escolha na sessao atual.

A chave nunca e salva em arquivos JSON do perfil, revisoes ou GitHub; seu valor e armazenado localmente com Windows DPAPI. **Ativar Gemini significa enviar pequenos recortes de tela ao Google** e pode consumir cota ou gerar custo em projetos pagos. As leituras da IA ainda precisam ser conferidas.


## Autoajuste das marcacoes ao trocar de video

**Problema:** a pre-calibracao de 4 mesas e os retangulos salvos de videos antigos podiam iniciar deslocados em gravacoes de 3 mesas. O erro era especialmente grave para as regioes roxa e azul, que anteriormente se sobrepunham e deixavam o OCR do saldo capturar partes do nick ou botoes.

**Correcao:** quando voce abre um novo video e a previa reconhece 1 a 4 mesas lado a lado, o aplicativo procura as **cartas claras do heroi na faixa inferior de cada mesa**, estima a posicao de cartas, nick e saldo e salva as coordenadas especificas para esse layout. A regiao do saldo deixa de se sobrepor ao nick no perfil inicial. O ajuste nao altera layouts diferentes e nao sobrescreve regioes marcadas manualmente na versao atual.

A barra de comandos agora inclui **AUTOAJUSTAR MARCACOES NESTE VIDEO**. Se estiver visualizando um trecho com as cartas do heroi abertas e as caixas permanecerem desalinhadas, clique nesse botao para forcar a calibracao do layout atual, sem afetar os outros layouts. O botao pede confirmacao antes de substituir marcas existentes. Se a imagem nao tiver evidencia suficiente das cartas, ele informa que o ajuste foi inconclusivo e **nao inventa coordenadas**.

A calibracao automatica usa heuristicas de brilho, por isso nao garante encontrar corretamente todas as mesas/temas de poker. **Antes de iniciar uma analise de horas, clique em Testar saldo e compare o numero lido com a gravacao.** O Gemini pode ajudar a ler saldos, mas nao corrige uma ROI sobre outro jogador.

As regioes geradas automaticamente sao salvas em `%LOCALAPPDATA%\CortadorPLO\marcacoes_padrao.json`. Regioes manuais permanecem prioritarias ate voce usar o botao de autoajuste e confirmar sua substituicao. Uma gravacao onde o jogador ainda nao recebeu cartas pode requerer navegar ate uma mao com cartas visiveis e clicar Mostrar frame.
