# Ciclo 67 — comparação visual por regiões manuais (somente revisão)

Escopo: `docs/VIDEO_ANALYZER_SCOPE.md`. O pipeline continua **offline e assíncrono**, sem mesas jogáveis, adversários, integração com poker real ou decisões ao vivo.

## Implementado

`activity_region_change_hints.py` recebe o `report.json` do pacote de contato FFmpeg do ciclo 65, PNGs auditados e um perfil JSON de regiões **manuais e não calibradas**. O perfil vincula o SHA-256 da gravação e até quatro mesas a retângulos normalizados de `board`, `hero_cards` e `pot`. Esses nomes são apenas hipóteses de layout: não há OCR, detecção de cartas, leitura do pote ou interpretação estratégica.

O módulo revalida o relatório original com `activity_visual_change_hints.py`, verifica hashes das imagens antes e depois da decodificação, recusa symlinks de diretórios e arquivos e calcula diferenças médias absolutas de luminância 48×48 dentro de cada ROI, sem comparar mesas/janelas diferentes. Quadros sem decodificação, fora do intervalo ou com PTS não crescentes são preservados como bloqueios. O JSON registra hashes canônicos do relatório, do perfil e das pistas globais, PTS decodificados, limiar fixo de pixels e a falta de calibração. **Não** autoriza cortes automáticos, boundaries, equity, EV ou classificação de erros.

## Uso

```bash
python video_analyzer/activity_region_change_hints.py \
  caminho/para/contact_sheet caminho/para/roi_profile.json saida.json \
  --pixel-threshold 0.12
```

Perfil de exemplo: `roi_profile_synthetic.json` no pacote de demonstração do ciclo. Cada `tables[].regions` contém retângulos `[x, y, largura, altura]` normalizados em `[0,1]`. Os retângulos de exemplo **não** correspondem a um layout de poker real. A saída nunca sobrescreve arquivos existentes. Para fixar a proveniência, usar `--expected-report-sha256` e `--expected-profile-sha256` com hashes **canônicos** do JSON.

## Testes e limitações

17 testes novos em `test_activity_region_change_hints.py` com evidências sintéticas, incluindo quatro mesas, PTS, determinismo, adulteração de PNG, symlinks, ROI inválida, ausência de região, perfil falsamente calibrado, hashes fixados e proteção contra sobrescrita. Testes específicos: `python -m unittest -q test_activity_region_change_hints test_activity_visual_change_hints test_activity_boundary_contact_sheet`.

Falta gravação autorizada para calibrar as regiões e aferir precisão real de OCR/reconstrução. Diferenças de pixels podem ser animações, cursor, efeitos visuais ou compressão. Não há prova de funcionamento em vídeos reais de 40–60 minutos.
