# PLO Trainee — revisão temporal offline das regiões de mesas

## Objetivo

Permitir conferir visualmente a mesma região de até quatro mesas em **três quadros aproximados** (10%, 50% e 90% da duração) antes de selecionar cortes. Opcionalmente a função Python aceita 2–5 timestamps crescentes e explícitos. Isso **não** demonstra estabilidade entre os quadros, nem comprova cartas, ações ou o instante exato da decisão.

## Uso

A partir da pasta `video_analyzer/`, depois de gerar um template de seleção **não aprovado** com `activity_review_clip_template.py`:

```bash
python activity_clip_selection_editor.py selecao_nao_aprovada.json revisao_timeline.html --video gravacao.mp4 --timeline
```

A página HTML é autocontida (JPEGs embutidos, sem dependências externas). Use **Quadro anterior / Próximo quadro**, confira visualmente os retângulos de cada mesa, marque a confirmação **individual** dos três quadros e, ao final, confirme as regiões e selecione os cortes. Alterar qualquer coordenada limpa as três confirmações e exige nova conferência. O arquivo JSON exportado deve passar pela validação Python do plano e do exportador FFmpeg; nenhuma decisão é aprovada por padrão.

`--timeline` não pode ser combinado com `--timestamp`. Para uma única prévia, o modo antigo `--video gravacao.mp4 --timestamp 1.0` continua disponível.

## Segurança e limitações

- Apenas arquivos locais MP4/WebM dentro dos limites do validador; hash SHA-256 do vídeo conferido **antes e depois** da extração; cada JPEG possui hash próprio.
- Extração por FFmpeg com busca rápida aproximada, `-nostdin`, sem `shell=True`, até cinco quadros, limite de 2 MiB por JPEG e 6 MiB somados.
- A validação do HTML rejeita timestamps fora de ordem, dimensões divergentes, JPEG adulterado e esquema inesperado. CSP bloqueia conexões e recursos externos.
- **A confirmação por quadro ocorre apenas na interface do navegador.** O JSON de seleção mantém o esquema anterior e não atesta criptograficamente quais quadros foram conferidos. Uma seleção JSON escrita manualmente ainda exige a validação Python e a confirmação humana das regiões, mas não prova a conferência temporal.
- Não há OCR calibrado com vídeos reais, rastreamento automático da posição das mesas, verificação exata de PTS, equity/EV real nem seleção automática de erros.

## Testes

`python -m unittest -v test_activity_clip_region_timeline test_activity_clip_region_preview test_activity_clip_selection_editor`

A demonstração sintética adicional usa Chromium/Playwright para conferir a troca de quadros, a obrigatoriedade de revisão de todos, o reset após edição e a geração de um MP4 pela cadeia de exportação existente. Isso não mede desempenho em sessões reais de PLO5/PLO6.
