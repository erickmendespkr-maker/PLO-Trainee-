# PLO Trainee — cortes MP4 com cartão de explicação humana (offline)

Este componente **não** identifica erros de pôquer. Ele recebe o manifesto de cortes que já foram selecionados e aprovados manualmente (`activity_review_clip_export.py`) e cria **novas cópias MP4** com um cartão final de quatro segundos. O trecho da gravação aparece **antes** do cartão, sem texto cobrindo as cartas. O cartão informa explicitamente que se trata de revisão humana sem conclusão de erro e que equity/EV não foram verificados.

## Execução local

Na pasta `video_analyzer`, com FFmpeg/FFprobe e filtro `drawtext` instalados:

```bash
python activity_review_clip_annotate.py \
  /caminho/clips/review_clip_manifest.json \
  /caminho/clips \
  /caminho/novos_clips_anotados
```

O diretório de saída **não pode existir** nem ficar dentro da pasta dos clipes de origem. São gerados MP4s `review_NNN_table_M.mp4` e `annotated_clip_manifest.json` com hashes SHA-256 do manifesto original, dos MP4s originais e dos MP4s anotados, além da duração, resolução e tipo de anotação. Os MP4s de origem não são modificados. O processo usa uma pasta temporária e só publica a saída ao concluir tudo.

## Limites e garantias

- Apenas manifestos `human_selected_neutral_review_clips_not_video_verified`, com `ready_for_equity_or_ev=false`, `authorized_for_ev_based_ranking=false` e `source_visual_content_verified=false`, são aceitos.
- Até 20 cortes por execução; cada original precisa corresponder ao tamanho, hash e metadados declarados. Nomes de arquivos arbitrários, caminhos relativos com `..`, symlinks e duplicatas são rejeitados.
- A explicação vem de um humano e não é evidência matemática. O cartão usa `drawtext` com `textfile` e `expansion=none` para evitar interpretação de caracteres fornecidos pelo usuário como expressões FFmpeg.
- A saída é 960×540 (com barras de enquadramento quando necessário), sem áudio, 12 fps e codificação H.264; cada cartão dura quatro segundos. É um protótipo de revisão, não um editor profissional.
- O manifesto de integridade **não** é assinatura criptográfica nem prova de que OCR, cartas, ações, ranges ou conclusões estratégicas estejam corretos.
- Sem conexão com jogos ao vivo, captura de tela, plataformas de apostas, credenciais ou serviços externos.

## Testes

```bash
cd video_analyzer
python -m unittest -v test_activity_review_clip_annotate
python -m unittest discover -s . -p 'test_*.py'
```

Os testes usam uma gravação **sintética** de quatro mesas, exportam quatro cortes reais com FFmpeg, geram cartões, decodificam um quadro do cartão e verificam hashes, metadados, bloqueios de EV, rejeição de adulteração e saída atômica em caso de erro.

**Bloqueio de produto:** falta uma gravação autorizada de PLO5/PLO6 para validar OCR, reconstrução de mãos, estabilidade das regiões das mesas e correção matemática. Nenhuma classificação automática de erro está liberada.
