# Ciclo 208 — pacote offline de sessão revisada

Escopo: gravações PLO5/PLO6 e revisão assíncrona, sem integração com poker real, adversários de IA, jogo ao vivo ou apostas.

## Entregue
- \`offline_session_bundle.py\`: exporta um ZIP novo e portátil contendo somente MP4 de cortes revisados, sidecars, manifesto de cortes, relatórios condicionais anexados (quando fornecidos), \`index.html\` regenerado e inventário SHA-256/tamanho de cada arquivo.
- O vídeo original **não é incluído**. O SHA-256 de origem é uma *declaração vinculada* à revisão, não prova da identidade de uma sessão real.
- O comando \`verify\` confere os membros do ZIP, rejeita duplicações, caminhos perigosos, arquivos inesperados, inconsistências de hashes e de metadados. Reexecuta a validação semântica da galeria e compara o HTML com a renderização dos dados validados.
- Sem sobrescrita; arquivos simbólicos são rejeitados; exportação interrompida elimina ZIP parcial; limites de 1 GiB por arquivo, 4 GiB descompactados e 406 arquivos.
- A verificação comprova **consistência interna**, não autenticidade externa, qualidade do OCR, identidade de jogador ou acerto estratégico.

## Comandos

\`\`\`bash
python video_analyzer/offline_session_bundle.py export clips session.zip auto_attachments.json
python video_analyzer/offline_session_bundle.py verify session.zip
\`\`\`

\`auto_attachments.json\` é opcional. Sem ele, o ZIP declara explicitamente que não há análises matemáticas anexadas.

## Testes locais
- 14 testes novos e 27 regressões dos módulos de galeria/associação: **41/41 aprovados** (unittest), com dados sintéticos.
- Exportação e revalidação do ZIP com o clipe MP4 sintético H001 (2,2 s, confirmado por FFprobe) e relatórios matemáticos artificiais.
- Testes de adulteração do ZIP, path traversal, membro duplicado, falso HTML re-hasheado, inconsistência de timestamps, symlinks, pares de análise ausentes e proteção contra sobrescrita.
- Nenhuma gravação real autorizada/anotada disponível. Não medidos OCR, reconstrução automática de mãos, desempenho 1080p/30 FPS, processamento real 40–60 min ou funcionamento no Windows. Suíte integral não executada.

## Próximo
Adicionar navegação explícita da interface de revisão para exportação de sessão, teste de portabilidade em Windows e comparação de reconhecimento visual contra gravação anotada autorizada.
