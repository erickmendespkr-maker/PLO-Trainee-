# Bloco 16 — candidatos de ações PLO5 (25/11/2026)

## Implementação

video_analyzer/plo5_action_candidates.py reutiliza os validadores de contexto e OCR do bloco 15, a geometria do bloco 14 e os recortes auditados do bloco 12. O perfil segue o do bloco 15 e acrescenta a cada assento a região action [x,y,width,height], relativa ao recorte; exige variante 5, 2–6 assentos declarados por mesa, e ROIs sem sobreposição. O assento é uma identificação condicionada ao perfil, não um nick ou uma identidade de hero confirmada.

CLI: python video_analyzer/plo5_action_candidates.py jobs.db JOB_ID profile.json new_report.json --threshold 0.75 --max-tasks 1024 --max-gap 10

Parser estrito de rótulos em português/inglês: fold, check, call, bet, raise, all-in e sinônimos explícitos. All-in permanece classe de rótulo, não prova de raise ou call. Aceita sufixo monetário explícito BB/chips/fichas para bet/call/raise/all-in; rejeita valores ambíguos, sem unidade, negativos e zero nesse sufixo. Não usa correspondência aproximada de palavras. ROI quase uniforme (amplitude de luminância <=12) é candidata a vazio, não prova de ausência de ação; OCR de baixa confiança ou texto não reconhecido permanece incerto.

Registra SHA do vídeo, manifesto, perfil e recorte, PTS, mesa/assento, ROI, SHA dos pixels RGB, texto e confiança OCR. Para rótulos reconhecidos lê o pote, blinds, stack e aposta visível do mesmo quadro; conversão em BB segue bloco 15. Não presume que esse quadro representa o estado anterior à decisão: custo do call e contribuição incremental permanecem null. Não deriva valor de ação pela diferença de stacks.

Agrupa rótulos iguais consecutivos por mesa/assento; cada episódio tem primeira/última observação e, quando possível, intervalo candidato desde a observação anterior. A janela máxima padrão é 10 s. PTS duplicados são excluídos do agrupamento, lacunas e incertezas interrompem continuidade, e episódios simultâneos não estabelecem ordenação das ações. Mudança de valor com o mesmo rótulo é preservada nas observações, não assumida como nova ação. Não atribui hand_id, não confirma mudança de mão, não conta episódios como jogadas, não autoriza EV ou cortes. Revalida o pacote e perfil ao final; sem alteração de estado do job.

## Testes

153 testes selecionados aprovados localmente (7 novos, 146 regressões), 26,293 s, Python 3.13.5. A suíte anterior inclui os classificadores reproduzidos no bloco 13, não é a suíte integral do repositório. Os arquivos locais do bloco 15 usados diretamente correspondem aos blobs publicados de plo5_context_candidates, plo5_card_candidates, plo5_ingest_job e ocr_probe.

MP4 sintético H.264, 640x240, 2 s, 5 fps: três recortes auditados, 24 tarefas de ROI, seis rótulos corretos (FOLD/CALL), dois episódios persistentes, pot 10 BB, stacks 120/70 BB, apostas visíveis 3/1 BB. O fixture tem rótulos estáticos simultâneos e não representa uma mão real. Testes adicionais de parser de seis classes, limites de unidade, repetição, incerteza, duplicatas, múltiplas mesas/assentos, variante, sobreposição, orçamento e adulteração. Apenas FOLD/CALL foram lidos por OCR no MP4; demais classes testadas pelo parser e/ou agrupamento.

## Pendências preservadas

Bloco 16 parcial: calibrar ROIs/rótulos reais, reconhecer ícones e ações breves, medir precisão e recall e reconstruir ordem e contribuições com evidência temporal suficiente. Limite de 1024 tarefas por padrão e 4096 máximo; requer lotes e refinamento temporal para sessões longas. O intervalo padrão de amostragem de 30 s do bloco 12 pode perder ações. Sem vídeo real neste ciclo. Blocos 11B, 13, 14 e 15 permanecem pendentes/parciais. Nenhuma mudança em main, deploy, automação, dados GTO ou vídeos privados.

Próximo bloco 17: unir observações de cartas, contexto e episódios por job/mesa/PTS, reconstruir rascunho de mão e identificação de hero, incluindo folds, sem transformar evidência insuficiente em histórico confirmado.
