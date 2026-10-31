# Ciclo 252 — revisão humana vinculada aos cortes MP4 (offline)

## Escopo
Novo módulo `video_analyzer/offline_reviewed_clip_manifest.py` associa o relatório validado de revisão humana (`street_human_review.json`) ao índice de evidências e clipes (`street_split_index.json`), gerando `reviewed_clip_manifest.json` e `reviewed_clip_manifest.html`. O HTML navega por mesa/mão, mostra valores confirmados, corrigidos e rejeitados e reproduz os MP4 previamente exportados. Não gera mãos jogáveis nem interage com plataformas de poker.

## Uso
```bash
python video_analyzer/offline_reviewed_clip_manifest.py \
  /caminho/street_human_review.json \
  /caminho/street_split_index.json \
  /caminho/diretorio_dos_mp4 \
  /caminho/diretorio_saida_vazio
```
Execute primeiro os validadores originais de evidências, revisão humana, índice e exportação de MP4. O novo módulo confere os vínculos entre os dois relatórios, SHA-256 de cada MP4, nomes de arquivos, identidade de mesa/mão, timestamps e integridade básica do JSON. O HTML usa caminhos relativos ao diretório dos clipes. Arquivos originais não são modificados; publicação dos dois arquivos é revertida se falhar.

## Testes executados no ambiente local (31/10/2026)
`python -m unittest -v test_offline_reviewed_clip_manifest.py`: **21 testes aprovados** em 2,398 s. Testes sintéticos abrangem quatro mesas, correção/rejeição, navegação HTML, integridade SHA-256, conflitos de proveniência, arquivos adulterados, traversal, symlinks, chaves JSON duplicadas, colisões e rollback. Demonstração independente gerou quatro MP4 sintéticos com FFmpeg e confirmou duração de 1,000 s por arquivo com FFprobe.

## Limitações e bloqueios
- A união de relatórios é **apenas navegação**. Não reexecuta integralmente os validadores de origem; execute-os antes de confiar na proveniência. O manifesto não prova que a mão/mesa foi identificada corretamente.
- Valores revisados são declarações humanas, não verdade óptica. Confiança não calibrada. Nenhum cálculo de equity, EV ou diagnóstico automático é autorizado.
- A verificação de SHA-256 comprova integridade do arquivo em relação ao índice, mas não comprova decodificação de todo MP4; FFprobe foi executado apenas na demonstração.
- Não testado com vídeos reais autorizados, sessões de 40–60 minutos, OCR real, Windows nem suíte integral.
- Falta vídeo anotado autorizado de 3–5 minutos para medir precisão de visão/OCR.

## Próximo
Preparar um contrato de entrada para Monte Carlo/EV que aceite somente dados revisados e suficientes, mantendo ranges e parâmetros explícitos, e bloqueie casos incompletos sem conclusões estratégicas.
