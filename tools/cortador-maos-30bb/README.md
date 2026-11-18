# Cortador de Mãos PLO — perdas acima de 30 BB

Aplicativo local para Windows 10/11, voltado à revisão de sessões gravadas **após o jogo**. Independente da plataforma web do PLO Trainee e isolado da branch principal.

## O que funciona no MVP

- Importa seis ou mais vídeos MP4 consecutivos e organiza uma linha do tempo única.
- Navega por frames das gravações com quatro mesas em quadrantes: mesa 1 = superior esquerda; 2 = superior direita; 3 = inferior esquerda; 4 = inferior direita.
- Lê históricos TXT convertidos no padrão PokerStars, calcula valor líquido das mãos do nick configurado (blinds, calls, raises, bets, devoluções e potes recebidos).
- Filtra perdas líquidas estritamente maiores que 30 BB (ou outro limite escolhido).
- Estima início/fim pelo horário das mãos e permite revisar e corrigir.
- Permite importar uma lista CSV ou cadastrar as mãos manualmente.
- Exporta cada mão em MP4 com apenas o quadrante da mesa, áudio e normalização 960×540 a 25 FPS.
- Gera indice_das_maos.csv, salva/reabre projeto e recorta inclusive intervalos que cruzam dois vídeos consecutivos.

## Limitações importantes

**Este MVP não detecta sozinho todas as perdas examinando apenas o vídeo.** Sem histórico ou CSV, você precisará marcar as mãos. OCR/visão computacional para verificar stack, cartas e resultado final não está implementado nesta versão. O programa também não calcula perdas a partir de oscilações de stack observadas na tela.

Com histórico DriveHUD, a sincronização depende do horário real de início da gravação e do horário/fuso do histórico. O fim da mão é estimado pelo começo da próxima mão na mesma mesa. A correspondência entre nome da mesa e quadrante é manual, e formatos proprietários de histórico podem não ser interpretados. **Revise os limites e valores de todas as mãos antes de entregar ao instrutor.**

Os vídeos devem ser realmente consecutivos, sem cortes ou lacunas. Caso contrário, use projetos separados.

## Instalar no Windows

Não precisa de Git. No GitHub, selecione a branch feature/cortador-maos-30bb, depois Code > Download ZIP. Extraia o ZIP e abra a pasta:

tools / cortador-maos-30bb

Dê dois cliques em **INICIAR_NO_WINDOWS.bat**.

- Se tiver Python com Tcl/Tk, a interface inicia.
- Caso contrário, o BAT pergunta se pode baixar o instalador oficial do Python 3.12.9, do python.org, para a sua conta.
- Você também precisa de **FFmpeg e FFprobe** no PATH (ou os dois EXEs na mesma pasta do BAT). Para conferir no CMD: ffmpeg -version e ffprobe -version.
- Não exige bibliotecas Python de terceiros.

Para gerar um arquivo EXE localmente: execute **GERAR_EXE_WINDOWS.bat**. Ele usa PyInstaller e salva o executável em dist / Cortador_Maos_PLO.exe. Esse EXE não vem pré-compilado e continuará precisando do FFmpeg e FFprobe.

## Uso para os seis vídeos

1. Clique em **Adicionar vídeos MP4**. Selecione Poker_Parte_01.mp4 a Poker_Parte_06.mp4 juntos.
2. Em **Seu nick**, coloque o apelido exatamente igual ao histórico (o inicial é ~Pulgar~).
3. Em **Início do 1º vídeo**, informe a data/hora real da gravação no formato AAAA-MM-DD HH:MM:SS. Exemplo apenas: 2026-11-17 20:04:04.
4. No DriveHUD 2, abra Sessions, clique com o botão direito na sessão e escolha **Export All Hands**, exportando histórico em texto quando disponível. Documentação oficial: https://drivehud.com/dh2-knowledge-base/how-do-i-export-my-hand-histories/
5. Clique em **Importar DriveHUD TXT** e ajuste o campo de diferença de horário caso o DriveHUD esteja em outro fuso.
6. Em **Mapear mesas do histórico**, vincule a identificação das mesas a cada um dos quadrantes 1–4.
7. Abra as mãos selecionadas e confira começo, fim, mesa e perda em BB. Assinale **Perda e limites conferidos**.
8. Selecione algumas mãos ou deixe a tabela sem seleção para exportar todas as elegíveis. Clique em **Exportar MP4**.

A pasta de saída terá mao_001...mp4, mao_002...mp4 e um índice CSV.

## Importação alternativa por CSV

Quando as perdas já foram detectadas por outra ferramenta, crie um CSV delimitado por ponto e vírgula com os cabeçalhos:

inicio_global;fim_global;mesa;perda_bb;descricao

Exemplo fictício:

00:11:55;00:13:14;2;35.5;Mao exemplo

Os horários são relativos ao início do primeiro vídeo, somando-se todas as partes consecutivas. O valor em BB é positivo e deve ter sido confirmado por outra fonte. Os valores do arquivo de exemplo são **fictícios** e não indicam perdas reais.

## Testes e estado de validação

Execute **py -3 testes.py** na pasta do programa. Foram adicionados testes de interpretação de apostas/raises, tempos, divisão de histórico e quadrantes. O ambiente de execução desta conversa está com falha, por isso não foi possível executar os testes nem verificar um recorte real ponta a ponta. É um MVP que ainda precisa de validação no Windows.

## Privacidade

Tudo ocorre localmente. O programa não envia vídeos, fichas ou histórico de mãos a qualquer serviço externo. Apenas o instalador opcional do Python e a instalação opcional do PyInstaller usam a internet. A ferramenta serve para análise de sessões encerradas, e não para decisões durante o jogo.
