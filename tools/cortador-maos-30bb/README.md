# Cortador PLO — Mãos perdidas ≥ 30 BB (OFFLINE)

Programa para Windows que identifica mãos em vídeos de poker PLO5 e recorta a mesa correspondente em MP4, sem Gemini, sem API e sem envio de imagens para servidores.

## Processo simples

1. **Localizar a mão:** o programa encontra as cinco cartas do jogador na parte inferior e identifica começo/fim, inclusive quando há 1, 2, 3 ou 4 mesas lado a lado.
2. **Medir o investimento:** lê o stack do herói antes e durante a mão com FFmpeg + Tesseract e estima a maior queda observada em BB. **Não supõe stack inicial de 100 BB.** O rebuy automático pode devolver o stack a 100 BB depois da mão sem apagar o dinheiro efetivamente investido.
3. **Verificar quem recebeu o pote:** analisa a **mesa inteira** perto do encerramento, buscando o pote central e os stacks de outros jogadores antes/depois. Só confirma automaticamente quando encontra um adversário com ganho persistente nos dois quadros finais, identifica o desaparecimento do pote e não há indício de side pot.
4. **Salvar MP4:** somente mãos com aporte estimado ≥ limite configurado **e** destino do pote confirmado são exportadas automaticamente, cada uma em arquivo MP4 com apenas aquela mesa.

O padrão é **30 BB inclusive**: 30,0 BB entra; 29,9 BB não. A análise do investimento não é igual à leitura do tamanho total do pote. Exemplo: pote de 80 BB, você contribuiu 20 BB — não é perda de 30 BB.

> **Limitação técnica:** um vídeo não é um histórico de apostas confiável. OCR pode falhar; animações podem ocultar a transferência; e ganhar parte de um side pot muda a perda líquida. A estimativa de stack durante a mão é apenas um indício, e não prova isolada. Se não houver confirmação confiável do destinatário, a mão ficará **PENDENTE**. Confira os MP4 antes de enviá-los ao instrutor.

## Como usar

1. Extraia o ZIP em uma pasta no Windows.
2. Execute **VERIFICAR_PROGRAMA.bat** para checar sintaxe e testes offline.
3. Abra **INICIAR_ANALISE_VIDEO.bat**.
4. Escolha o vídeo com **Adicionar 1 vídeo completo ou várias partes**. Deixe **Disposição: Automático** se a quantidade de mesas variar.
5. Mantenha o retângulo verde **HUD único**, que inclui suas cartas, nick e saldo. Você pode ajustar uma única caixa e o programa a replica nas mesas do mesmo layout. Confira com **Testar saldo** e **Verificar nick no frame**.
6. Preencha seu nick e o valor de 1 BB e clique **ANALISAR VÍDEO(S)**. As três etapas são executadas localmente.
7. Se **Salvar MP4 de perdas confirmadas** estiver marcado, os vídeos comprovados serão exportados para a pasta predefinida.

O endereço inicial dos arquivos no Windows é:

`%USERPROFILE%\Videos\Cortador PLO\Maos analisadas`

Use **Alterar pasta** para selecionar outra pasta. O destino fica em `%LOCALAPPDATA%\CortadorPLO\preferencias.json`, preservado entre atualizações. Ajustes da marcação são guardados em `marcacoes_padrao.json` no mesmo diretório, sem precisar reconfigurar em cada execução.

## Quando o programa não tiver certeza

- **PRIORIDADE**: queda durante a mão sugere investimento ≥ 30 BB, mas o pote ainda precisa ser confirmado.
- **PERDA CONFIRMADA — POTE PARA ADVERSÁRIO (OFFLINE)**: sinal de aporte e transferência foi considerado suficiente; exporta o MP4 automaticamente.
- **PENDENTE**: não houve prova visual suficiente. Não exporta como perda.
- **EXPORTAR PARA REVISÃO**: gera MP4s de mãos candidatas, claramente rotulados como não confirmados, para você assistir e conferir.

Para confirmar uma mão pendente, selecione-a, informe **perda líquida real em BB**, indique o destino do pote e clique **Conferir/Salvar**. Depois clique **EXPORTAR PERDAS**. Em caso de side pot, informe a perda líquida depois de descontar o que você recuperou.

As revisões são salvas automaticamente em:

`%LOCALAPPDATA%\CortadorPLO\ultima_revisao.json`

O botão **Abrir última revisão** recupera a sessão anterior se os arquivos MP4 originais permanecerem nos caminhos esperados. **ESTIMAR APORTES (OFFLINE)** reaproveita esses horários sem repetir a varredura inicial.

## Dependências

- Python 3.12 com Pillow e Tkinter
- FFmpeg e FFprobe
- Tesseract OCR (idioma inglês basta)

Se necessário, use **INSTALAR_TUDO_WINDOWS.bat**. A execução da análise **não precisa de conexão com a internet**.

## Verificação

Os testes locais em **VERIFICAR_PROGRAMA.bat** abrangem detecção de mesas, HUD, valores de BB, rebuy automático, pastas e premiação do pote em exemplos sintéticos. Eles não substituem um teste com a gravação real; valide primeiro um vídeo curto e confira o índice de cortes e os desfechos.
