# Ciclo 232 — consolidação offline por mão/street e evidência visual

## Escopo e entrega
- `offline_visual_hand_summary.py` consolida dois ledgers locais: revisão humana de mão/street e importação da revisão visual.
- Verifica hash SHA-256 do ledger de revisão, vínculo de hash do vídeo declarado, versão e estado dos ledgers, quantidade de mãos/campos, identidades mão/mesa/campo/slot, timestamps, hashes e contadores de estados visuais.
- Organiza os campos declarados por preflop/flop/turn/river/unknown, mantendo valores, estados de revisão e timestamps **não autenticados**.
- Diagnostica variante não confirmada, cartas privadas/flop incompletos, duplicidade de cartas declaradas, ações/pote/stack ausentes e street de ação não verificada.
- Rejeita adulteração de valores e proveniência, duplicações, cinco mesas, contadores incoerentes, evidências malformadas, JSON duplicado e NaN.
- Preserva `eligible_for_equity: 0`, `equity_or_ev_calculated: false`, `math_ready: false` em todas as mãos; não chama o motor matemático.

## Testes executados
- 26 testes sintéticos novos, aprovados.
- 218 testes selecionados de regressão e do novo módulo, aprovados no ambiente Linux local.
- Repetição isolada em diretório temporário, com os módulos necessários extraídos e sem rede.
- Demo de quatro mesas artificiais; nenhum dado de pôquer real foi usado.

## Uso
`python video_analyzer/offline_visual_hand_summary.py reviewed.json visual_import.json novo_resumo.json`

O arquivo de saída deve ser novo. Os hashes e os estados humanos não autenticam o conteúdo dos quadros.

## Limitações e bloqueios
Falta gravação autorizada e anotada de PLO5/PLO6 para medir OCR, segmentação, detecção de mãos e precisão visual. Não houve validação de 40–60 minutos, Windows, suíte integral ou exportação MP4 ponta a ponta. Nenhuma alteração em main, produção, credenciais ou gastos.

## Próximo ciclo
Criar um contrato matemático separado com hipóteses explícitas de ranges, cartas completas, parâmetros de Monte Carlo e critérios de confiança, sem promover automaticamente revisões OCR/visuais a fatos.
